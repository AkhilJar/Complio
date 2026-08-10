from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    """What the api gives back for an uploaded document.

    Metadata only: markdown_content would bloat every list response, and
    minio_key is internal placement the client has no business knowing.
    """

    #from_attributes so a sqlalchemy row can be returned directly
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    filename: str
    uploaded_at: datetime
