import secrets
import uuid
from sqlalchemy import Column, String, Boolean, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.infra.db.database import Base


class TryOnJob(Base):
    __tablename__ = "tryon_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    status = Column(String, nullable=False, default="queued")  # queued|processing|done|error

    person_image_path = Column(String, nullable=False)
    garment_image_path = Column(String, nullable=False)
    result_image_path = Column(String, nullable=True)

    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)

    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=2)

    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String, nullable=False, default="default")
    key = Column(String, nullable=False, unique=True, index=True)

    is_active = Column(Boolean, nullable=False, default=True)
    rpm_limit = Column(Integer, nullable=False, default=60)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @staticmethod
    def generate() -> str:
        return secrets.token_urlsafe(32)
