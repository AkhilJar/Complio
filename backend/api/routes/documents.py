import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from api.schemas import DocumentCreate, DocumentRead
from database.models import UserDocument
from database.session import get_db

router = APIRouter()

#1 MB of text. compliance documents are prose, so this is generous — the whole
#body is held in memory to hash it, and postgres stores it in one column
MAX_CONTENT_BYTES = 1024 * 1024


@router.post("/documents", response_model=DocumentRead, status_code=201)
def create_document(
    payload: DocumentCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> UserDocument:
    content = payload.content
    if not content.strip():
        raise HTTPException(status_code=400, detail="document content is empty")

    #measured in bytes, not characters, since that is what actually gets
    #stored and a multi-byte character costs more than one
    size = len(content.encode("utf-8"))
    if size > MAX_CONTENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"content exceeds the {MAX_CONTENT_BYTES // 1024} KB limit",
        )

    #hash the content, so resubmitting the same document is recognised
    #regardless of the filename it arrives under
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    existing = (
        db.query(UserDocument).filter(UserDocument.content_hash == content_hash).first()
    )
    if existing is not None:
        #idempotent: hand back what is already stored rather than duplicating
        #it, and say 200 instead of 201 because nothing was created
        response.status_code = 200
        return existing

    document = UserDocument(
        document_id=uuid.uuid4(),
        filename=payload.filename,
        #minio_key stays null: nothing is written to object storage for text
        markdown_content=content,
        content_hash=content_hash,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(db: Session = Depends(get_db)) -> list[UserDocument]:
    return db.query(UserDocument).order_by(UserDocument.uploaded_at.desc()).all()


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> UserDocument:
    document = db.get(UserDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document
