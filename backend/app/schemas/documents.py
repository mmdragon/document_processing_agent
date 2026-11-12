from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ProcessingStatus = Literal["uploaded", "processing", "processed", "failed", "reviewed"]


class DocumentUploadResponse(BaseModel):
    document_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    status: ProcessingStatus = "uploaded"
