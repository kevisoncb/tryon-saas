from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TryOnCreateResponse(BaseModel):
    job_id: UUID
    status: str


class TryOnStatusResponse(BaseModel):
    job_id: UUID
    status: str
    person_image_path: str
    garment_image_path: str
    result_image_path: Optional[str] = None
    result_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ErrorResponse(BaseModel):
    detail: str
