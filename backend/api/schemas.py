from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    """A document submitted as text — no file, no upload."""

    filename: str = Field(min_length=1, max_length=255)
    content: str


class DocumentRead(BaseModel):
    """What the api gives back for a stored document.

    Metadata only: the content itself would bloat every list response.
    """

    #from_attributes so a sqlalchemy row can be returned directly
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    filename: str
    uploaded_at: datetime
