import time
from ftplib import FTP, all_errors
from io import BytesIO

from config import settings

#the TLC explicitly asks data consumers to use this FTP site instead of mining
#www.legis.state.tx.us, so anonymous FTP is the sanctioned path — no api key
ANONYMOUS_USER = "anonymous"
ANONYMOUS_PASSWORD = "complio@example.com"


class TxFtpClient:
    """Thin wrapper over ftplib for the Texas Legislature anonymous FTP site.

    Downloads stream through memory into the caller's hands — nothing is
    written to the host filesystem, because Postgres is the only store.
    """

    def __init__(self, host: str = None, delay: float = None, retries: int = 3):
        self.host = host or settings.tx_ftp_host
        #a courtesy pause between requests so we never hammer a public server
        self.delay = settings.tx_ftp_delay if delay is None else delay
        self.retries = retries
        self.ftp: FTP | None = None

    #context manager so the control connection always gets closed, even on error
    def __enter__(self) -> "TxFtpClient":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def connect(self) -> None:
        self.ftp = FTP(self.host, timeout=settings.tx_ftp_timeout)
        self.ftp.login(ANONYMOUS_USER, ANONYMOUS_PASSWORD)

    def close(self) -> None:
        if self.ftp is None:
            return
        try:
            self.ftp.quit()
        except all_errors:
            #server may have dropped us already; nothing useful to do about it
            pass
        finally:
            self.ftp = None

    #FTP control connections drop often on long runs, so every call routes
    #through here: sleep, try, and on failure reconnect and try again
    def _with_retry(self, operation):
        last_error = None
        for attempt in range(self.retries):
            time.sleep(self.delay)
            try:
                if self.ftp is None:
                    self.connect()
                return operation()
            except all_errors as exc:
                last_error = exc
                self.close()
                #back off a little further each time before reconnecting
                time.sleep(self.delay * (attempt + 1))
        raise RuntimeError(
            f"FTP operation failed after {self.retries} attempts: {last_error}"
        )

    def list_dir(self, path: str) -> list[str]:
        """Bare entry names (not full paths) sorted for deterministic runs."""

        def operation():
            #nlst returns full paths on this server, so keep only the leaf
            return sorted(entry.rsplit("/", 1)[-1] for entry in self.ftp.nlst(path))

        return self._with_retry(operation)

    def download_text(self, path: str) -> str:
        """Fetch a file into memory and decode it to str."""

        def operation():
            buffer = BytesIO()
            self.ftp.retrbinary(f"RETR {path}", buffer.write)
            return buffer.getvalue()

        raw = self._with_retry(operation)
        #these files are legacy windows-encoded; utf-8 first, then cp1252,
        #which covers the smart quotes and dashes in the bill text
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("cp1252", errors="replace")
