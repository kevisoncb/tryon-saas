from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class TryOnCreateResponse(BaseModel):
    job_id: UUID
    status: str


class TryOnStatusResponse(BaseModel):
    job_id: UUID
    status: str
    person_image_path: str
    garment_image_path: str
    result_image_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
