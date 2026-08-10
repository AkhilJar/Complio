import hashlib
import re
import uuid

import pymupdf
import pymupdf4llm
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from api.schemas import DocumentRead
from database.models import UserDocument
from database.session import get_db
from storage.client import delete_object, ensure_bucket, upload_bytes

router = APIRouter()

#20 MB. compliance documents are text, not media — anything larger is a
#mistake or an abuse, and the whole file is held in memory while we hash it
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

PDF_CONTENT_TYPE = "application/pdf"


def _extract_markdown(data: bytes) -> str:
    """PDF bytes -> markdown. Mechanical extraction, no model involved."""
    #opened from a stream rather than a path so the upload never touches disk
    with pymupdf.open(stream=data, filetype="pdf") as document:
        return pymupdf4llm.to_markdown(document)


def _has_extractable_text(markdown: str) -> bool:
    """True only if the markdown carries content, not just page furniture.

    pymupdf4llm emits a '-----' separator per page even when the page holds
    no text at all, so a scanned image yields '-----\\n\\n' — non-empty to a
    plain strip(), yet carrying nothing to embed later.
    """
    without_separators = re.sub(r"^\s*-{3,}\s*$", "", markdown, flags=re.MULTILINE)
    return bool(without_separators.strip())


@router.post("/documents", response_model=DocumentRead, status_code=201)
def upload_document(
    response: Response,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UserDocument:
    filename = file.filename or ""
    #check both: the extension alone is trivially renamed, and the content
    #type alone is whatever the client chose to claim
    if file.content_type != PDF_CONTENT_TYPE or not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only pdf uploads are accepted")

    data = file.file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )
    if not data:
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    #hash the original bytes, so re-uploading the same pdf is recognised
    #regardless of the filename it arrives under
    content_hash = hashlib.sha256(data).hexdigest()

    existing = (
        db.query(UserDocument).filter(UserDocument.content_hash == content_hash).first()
    )
    if existing is not None:
        #idempotent: hand back what is already stored rather than duplicating
        #it, and say 200 instead of 201 because nothing was created
        response.status_code = 200
        return existing

    try:
        markdown = _extract_markdown(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"could not read pdf: {exc}")

    #a scanned image carries no text layer, so extraction comes back blank.
    #rejecting here — before anything is stored — is what keeps minio free of
    #objects that no row will ever point at
    if not _has_extractable_text(markdown):
        raise HTTPException(
            status_code=422,
            detail="no extractable text in pdf (likely a scanned image)",
        )

    document_id = uuid.uuid4()
    #key derived from the id, so the object is traceable back to its row and
    #two uploads of the same filename cannot collide
    minio_key = f"documents/{document_id}.pdf"

    ensure_bucket()
    upload_bytes(data, minio_key, content_type=PDF_CONTENT_TYPE)

    document = UserDocument(
        document_id=document_id,
        filename=filename,
        minio_key=minio_key,
        markdown_content=markdown,
        content_hash=content_hash,
    )
    try:
        db.add(document)
        db.commit()
    except Exception:
        #the row is what makes the object reachable; without it the upload is
        #garbage, so roll it back rather than leaking it
        db.rollback()
        delete_object(minio_key)
        raise

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
