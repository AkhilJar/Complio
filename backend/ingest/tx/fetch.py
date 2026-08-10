import argparse
import hashlib
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert

from config import settings
from database.models import Bill, BillText
from database.session import SessionLocal
from ingest.tx.ftp_client import TxFtpClient

#/bills/<session>/billtext/html/<bill type>/<grouping of 100>/<file>
FTP_ROOT = "/bills/{session}/billtext/html/{bill_type}"

#version suffix before .htm: I=Introduced, H/S=Committee Report, E=Engrossed,
#F=Enrolled. v1 ingests Introduced only — every filed bill has one, while the
#later stages exist only for bills that advanced
INTRODUCED_SUFFIX = "I.htm"

#some bills only exist as PDF and ship an html placeholder instead; storing
#that boilerplate as extracted_text would be worse than storing nothing
STUB_MARKER = "An HTML version of this bill is not available"


def bill_number_from_filename(filename: str) -> str:
    """HB00001I.htm -> HB1 (the zero padding is for directory sorting only)."""
    stem = filename[: -len(INTRODUCED_SUFFIX)]
    match = re.match(r"^([A-Z]+)(\d+)$", stem)
    if not match:
        raise ValueError(f"unexpected bill filename: {filename}")
    prefix, digits = match.groups()
    return f"{prefix}{int(digits)}"


def extract_text(html: str) -> str:
    """Plain text from bill html, with runs of whitespace collapsed."""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    #the markup is word-processor export, so it is dense with nbsp and
    #line-wrapping that carries no meaning once the tags are gone
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_title(text: str) -> str | None:
    """The bill caption — 'relating to ...' — if the text carries one."""
    match = re.search(r"\bAN ACT\s+(relating to .*?\.)(?:\s|$)", text, re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


def iter_introduced_files(ftp: TxFtpClient, session: str, bill_type: str):
    """Yield (grouping, filename) for introduced bills, lowest number first."""
    root = FTP_ROOT.format(session=session, bill_type=bill_type)
    for grouping in ftp.list_dir(root):
        for filename in ftp.list_dir(f"{root}/{grouping}"):
            if filename.endswith(INTRODUCED_SUFFIX):
                yield grouping, filename


def upsert_bill(db, bill_id: str, session: str, bill_type: str,
                bill_number: str, title: str | None, fetched_at: datetime) -> None:
    #on conflict update rather than insert: re-running the ingest should
    #refresh a bill in place, never accumulate duplicates
    statement = insert(Bill).values(
        bill_id=bill_id,
        session=session,
        bill_type=bill_type,
        bill_number=bill_number,
        title=title,
        fetched_at=fetched_at,
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["bill_id"],
            set_={
                "session": statement.excluded.session,
                "bill_type": statement.excluded.bill_type,
                "bill_number": statement.excluded.bill_number,
                "title": statement.excluded.title,
                "fetched_at": statement.excluded.fetched_at,
            },
        )
    )


def upsert_bill_text(db, bill_id: str, raw_html: str, extracted: str,
                     text_hash: str, fetched_at: datetime) -> None:
    #conflicts on the unique bill_id, which is what keeps this to one text
    #row per bill — v1 overwrites instead of versioning
    statement = insert(BillText).values(
        bill_id=bill_id,
        raw_html=raw_html,
        extracted_text=extracted,
        text_hash=text_hash,
        fetched_at=fetched_at,
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["bill_id"],
            set_={
                "raw_html": statement.excluded.raw_html,
                "extracted_text": statement.excluded.extracted_text,
                "text_hash": statement.excluded.text_hash,
                "fetched_at": statement.excluded.fetched_at,
            },
        )
    )


def ingest(limit: int, session: str, bill_type: str) -> int:
    stored = 0
    skipped = 0
    db = SessionLocal()
    try:
        with TxFtpClient() as ftp:
            for grouping, filename in iter_introduced_files(ftp, session, bill_type):
                if stored >= limit:
                    break

                path = f"{FTP_ROOT.format(session=session, bill_type=bill_type)}/{grouping}/{filename}"
                raw_html = ftp.download_text(path)
                extracted = extract_text(raw_html)

                if STUB_MARKER in extracted:
                    skipped += 1
                    print(f"  skip {filename}: pdf-only placeholder")
                    continue

                bill_number = bill_number_from_filename(filename)
                bill_id = f"{session.upper()}_{bill_number}"
                #hash the html, not the extracted text, so a change is caught
                #even if our extraction logic changes later
                text_hash = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
                fetched_at = datetime.now(timezone.utc)

                #bill first: the foreign key requires the parent row to exist
                upsert_bill(db, bill_id, session, bill_type, bill_number,
                            extract_title(extracted), fetched_at)
                upsert_bill_text(db, bill_id, raw_html, extracted, text_hash, fetched_at)
                #commit per bill so an interrupted run keeps what it fetched
                db.commit()

                stored += 1
                print(f"  {stored:2}. {bill_id:10} {len(extracted):>8} chars  {text_hash[:12]}")
    finally:
        db.close()

    print(f"stored {stored} bills ({skipped} skipped)")
    return stored


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Texas bill text into Postgres")
    #default caps the sample: this walks a public ftp site, not a local file
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--session", default=settings.tx_session)
    parser.add_argument("--bill-type", default="house_bills")
    args = parser.parse_args()

    print(f"ingesting up to {args.limit} {args.bill_type} from {args.session}")
    ingest(args.limit, args.session, args.bill_type)


if __name__ == "__main__":
    main()
