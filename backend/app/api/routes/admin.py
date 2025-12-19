from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import rate_limit
from app.infra.db.database import get_db
from app.infra.db.crud import list_jobs

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/jobs")
def admin_list_jobs(
    status: str | None = None,
    limit: int = 50,
    _api_key: str = Depends(rate_limit),
    db: Session = Depends(get_db),
):
    items = list_jobs(db, status=status, limit=min(max(limit, 1), 200))
    return [{
        "job_id": str(j.id),
        "status": j.status,
        "attempts": int(j.attempts or 0),
        "created_at": j.created_at.isoformat(),
        "updated_at": j.updated_at.isoformat(),
    } for j in items]
