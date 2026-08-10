import uuid

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import Column

from database.session import Base


class Bill(Base):
    """One row per bill we have seen on the Texas Legislature FTP site."""

    __tablename__ = "bills"

    #natural key like "89R_HB1" — the legislature already gives every bill a
    #stable identifier, so a surrogate id would add nothing but indirection
    bill_id = Column(Text, primary_key=True)
    session = Column(Text, nullable=False)
    bill_type = Column(Text, nullable=False)
    bill_number = Column(Text, nullable=False)
    #nullable: the caption is parsed out of the html and is not always present
    title = Column(Text)
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    text = relationship("BillText", back_populates="bill", uselist=False)


class BillText(Base):
    """The bill's text, kept both verbatim and as plain text.

    v1 stores exactly one row per bill: a re-fetch overwrites in place rather
    than appending a version, which the unique constraint on bill_id enforces.
    """

    __tablename__ = "bill_texts"

    text_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bill_id = Column(Text, ForeignKey("bills.bill_id"), nullable=False)
    #kept verbatim so re-extraction never requires re-fetching from the ftp
    raw_html = Column(Text, nullable=False)
    extracted_text = Column(Text, nullable=False)
    #sha256 of raw_html — lets a later run tell "changed" from "unchanged"
    #without diffing megabytes of markup
    text_hash = Column(Text, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    bill = relationship("Bill", back_populates="text")

    #the one-text-per-bill rule, enforced in the database rather than in code
    #so the upsert has something to conflict on
    __table_args__ = (UniqueConstraint("bill_id", name="uq_bill_texts_bill_id"),)
