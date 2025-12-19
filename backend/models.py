import uuid
from sqlalchemy import Column, String, DateTime, func, Integer, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class TryOnJob(Base):
    __tablename__ = "tryon_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # queued | processing | done | error
    status = Column(String, nullable=False, default="queued")

    person_image_path = Column(String, nullable=False)
    garment_image_path = Column(String, nullable=False)
    result_image_path = Column(String, nullable=True)

    error_message = Column(Text, nullable=True)
    last_error = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    processing_started_at = Column(DateTime(timezone=True), nullable=True)

    # associação com API Key
    api_key_id = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, default="default")
    key = Column(String, nullable=False, unique=True, index=True)

    is_active = Column(Boolean, nullable=False, default=True)
    rpm_limit = Column(Integer, nullable=False, default=60)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
