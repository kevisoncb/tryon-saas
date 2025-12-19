# backend/app/infra/db/crud.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.infra.db.models import (
    ApiKey,
    Membership,
    Plan,
    Subscription,
    Tenant,
    TryOnJob,
    UsageEvent,
    User,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _is_sqlite(db: Session) -> bool:
    try:
        name = db.bind.dialect.name  # type: ignore[union-attr]
        return name == "sqlite"
    except Exception:
        return False


# -----------------------------------------------------------------------------
# API KEYS
# -----------------------------------------------------------------------------
def get_api_key(db: Session, key: str) -> Optional[ApiKey]:
    stmt = select(ApiKey).where(ApiKey.key == key, ApiKey.is_active.is_(True))
    return db.execute(stmt).scalar_one_or_none()


def touch_api_key_last_used(db: Session, api_key: ApiKey) -> None:
    api_key.last_used_at = utcnow()
    db.commit()


def create_api_key(
    db: Session,
    *,
    name: str,
    tenant_id: Optional[UUID],
    rpm_limit: int = 60,
    scopes: Optional[str] = None,
) -> ApiKey:
    row = ApiKey(
        name=name,
        key=ApiKey.generate(),
        tenant_id=tenant_id,
        rpm_limit=int(rpm_limit),
        scopes=scopes,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def revoke_api_key(db: Session, api_key: ApiKey) -> None:
    api_key.is_active = False
    api_key.revoked_at = utcnow()
    db.commit()


# -----------------------------------------------------------------------------
# JOBS
# -----------------------------------------------------------------------------
def create_job(
    db: Session,
    person_path: str,
    garment_path: str,
    *,
    tenant_id: Optional[UUID] = None,
    api_key_id: Optional[UUID] = None,
    requested_by_user_id: Optional[UUID] = None,
) -> TryOnJob:
    job = TryOnJob(
        person_image_path=person_path,
        garment_image_path=garment_path,
        status="queued",
        tenant_id=tenant_id,
        api_key_id=api_key_id,
        requested_by_user_id=requested_by_user_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: UUID) -> Optional[TryOnJob]:
    stmt = select(TryOnJob).where(TryOnJob.id == job_id)
    return db.execute(stmt).scalar_one_or_none()


def list_jobs(db: Session, status: Optional[str], limit: int = 50) -> List[TryOnJob]:
    stmt = select(TryOnJob).order_by(TryOnJob.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(TryOnJob.status == status)
    return list(db.execute(stmt).scalars().all())


def mark_processing(db: Session, job: TryOnJob) -> None:
    job.status = "processing"
    job.processing_started_at = utcnow()
    job.error_code = None
    job.error_message = None
    job.attempts = int(job.attempts or 0) + 1
    db.commit()


def mark_done(db: Session, job: TryOnJob, result_path: str, *, processing_ms: Optional[int] = None) -> None:
    job.status = "done"
    job.result_image_path = result_path
    job.completed_at = utcnow()
    job.processing_ms = processing_ms
    job.error_code = None
    job.error_message = None
    db.commit()


def mark_error(db: Session, job: TryOnJob, error_code: str, error_message: str) -> None:
    job.status = "error"
    job.error_code = error_code
    job.error_message = (error_message or "")[:2000]
    job.completed_at = utcnow()
    db.commit()


def fail_stuck_jobs(db: Session, timeout_seconds: int = 240) -> int:
    now = utcnow()
    cutoff = now - timedelta(seconds=timeout_seconds)

    stmt = select(TryOnJob).where(
        TryOnJob.status == "processing",
        TryOnJob.processing_started_at.is_not(None),
        TryOnJob.processing_started_at < cutoff,
    )
    jobs = list(db.execute(stmt).scalars().all())

    for j in jobs:
        j.status = "error"
        j.error_code = "WORKER_TIMEOUT"
        j.error_message = "Job ficou travado em processing e foi finalizado por timeout."
        j.completed_at = now

    if jobs:
        db.commit()

    return len(jobs)


def claim_next_job(db: Session) -> Optional[TryOnJob]:
    try:
        stmt = (
            select(TryOnJob)
            .where(TryOnJob.status == "queued")
            .order_by(TryOnJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = db.execute(stmt).scalar_one_or_none()
        if not job:
            db.rollback()
            return None

        job.status = "processing"
        job.processing_started_at = utcnow()
        job.error_code = None
        job.error_message = None
        job.attempts = int(job.attempts or 0) + 1

        db.commit()
        db.refresh(job)
        return job

    except (OperationalError, TypeError):
        db.rollback()

        stmt = (
            select(TryOnJob)
            .where(TryOnJob.status == "queued")
            .order_by(TryOnJob.created_at.asc())
            .limit(1)
        )
        job = db.execute(stmt).scalar_one_or_none()
        if not job:
            return None

        job.status = "processing"
        job.processing_started_at = utcnow()
        job.error_code = None
        job.error_message = None
        job.attempts = int(job.attempts or 0) + 1

        db.commit()
        db.refresh(job)
        return job


# -----------------------------------------------------------------------------
# SaaS: Tenant / User / Membership
# -----------------------------------------------------------------------------
def create_tenant(db: Session, *, name: str, slug: str) -> Tenant:
    row = Tenant(name=name, slug=slug, is_active=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_tenant_by_slug(db: Session, slug: str) -> Optional[Tenant]:
    stmt = select(Tenant).where(Tenant.slug == slug)
    return db.execute(stmt).scalar_one_or_none()


def create_user(db: Session, *, email: str, password_hash: Optional[str] = None, is_superadmin: bool = False) -> User:
    row = User(email=email.lower().strip(), password_hash=password_hash, is_superadmin=is_superadmin, is_active=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    stmt = select(User).where(User.email == email.lower().strip())
    return db.execute(stmt).scalar_one_or_none()


def add_membership(db: Session, *, tenant_id: UUID, user_id: UUID, role: str = "owner") -> Membership:
    row = Membership(tenant_id=tenant_id, user_id=user_id, role=role)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# -----------------------------------------------------------------------------
# SaaS: Plans / Subscription
# -----------------------------------------------------------------------------
def ensure_default_plans(db: Session) -> None:
    existing = {p.code for p in db.execute(select(Plan)).scalars().all()}
    to_create = []

    if "free" not in existing:
        to_create.append(Plan(code="free", name="Free", jobs_per_day=50, max_upload_mb=10, max_resolution=1024, priority=0, is_active=True))
    if "pro" not in existing:
        to_create.append(Plan(code="pro", name="Pro", jobs_per_day=500, max_upload_mb=20, max_resolution=2048, priority=10, is_active=True))

    if to_create:
        db.add_all(to_create)
        db.commit()


def get_active_subscription(db: Session, tenant_id: UUID) -> Optional[Subscription]:
    stmt = select(Subscription).where(Subscription.tenant_id == tenant_id, Subscription.status == "active")
    return db.execute(stmt).scalar_one_or_none()


def set_subscription(db: Session, *, tenant_id: UUID, plan_code: str) -> Subscription:
    plan = db.execute(select(Plan).where(Plan.code == plan_code, Plan.is_active.is_(True))).scalar_one_or_none()
    if not plan:
        raise ValueError("PLAN_NOT_FOUND")

    actives = db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id, Subscription.status == "active")).scalars().all()
    now = utcnow()
    for s in actives:
        s.status = "canceled"
        s.ends_at = now

    sub = Subscription(tenant_id=tenant_id, plan_id=plan.id, status="active")
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def get_plan_for_tenant(db: Session, tenant_id: UUID) -> Plan:
    sub = get_active_subscription(db, tenant_id)
    if not sub:
        plan = db.execute(select(Plan).where(Plan.code == "free")).scalar_one_or_none()
        if plan:
            return plan
        raise ValueError("NO_PLAN_CONFIGURED")
    return db.execute(select(Plan).where(Plan.id == sub.plan_id)).scalar_one()


# -----------------------------------------------------------------------------
# SaaS: Usage ledger + enforcement
# -----------------------------------------------------------------------------
def record_usage_event(
    db: Session,
    *,
    tenant_id: UUID,
    event_type: str,
    units: int = 1,
    api_key_id: Optional[UUID] = None,
    job_id: Optional[UUID] = None,
) -> UsageEvent:
    ev = UsageEvent(
        tenant_id=tenant_id,
        api_key_id=api_key_id,
        job_id=job_id,
        event_type=event_type,
        units=int(units),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def count_usage_today(db: Session, tenant_id: UUID, *, event_type: str = "tryon_created") -> int:
    """
    Compatível com Postgres e SQLite.
    - Postgres: date_trunc('day', ...)
    - SQLite: strftime('%Y-%m-%d', ...)
    """
    if _is_sqlite(db):
        stmt = select(func.coalesce(func.sum(UsageEvent.units), 0)).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.event_type == event_type,
            func.strftime("%Y-%m-%d", UsageEvent.created_at) == func.strftime("%Y-%m-%d", func.current_timestamp()),
        )
    else:
        stmt = select(func.coalesce(func.sum(UsageEvent.units), 0)).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.event_type == event_type,
            func.date_trunc("day", UsageEvent.created_at) == func.date_trunc("day", func.now()),
        )

    return int(db.execute(stmt).scalar_one() or 0)


def enforce_plan_limits_for_new_job(db: Session, *, tenant_id: UUID) -> None:
    plan = get_plan_for_tenant(db, tenant_id)
    used = count_usage_today(db, tenant_id, event_type="tryon_created")
    if used >= int(plan.jobs_per_day):
        raise ValueError("PLAN_QUOTA_EXCEEDED")
