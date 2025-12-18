import uuid
from sqlalchemy import Column, String, DateTime, func
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

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
