from pydantic_settings import BaseSettings


#reads settings from environment variables (set by compose)
class Settings(BaseSettings):
    database_url: str
    #tests run against their own database so a test run can never touch dev
    #data. empty means "same server as database_url, but the complio_test
    #database", which is what conftest derives
    test_database_url: str = ""
    #object storage — points at the minio container now, at s3/r2 after deploy
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    #texas legislature ftp — defaults live here rather than in .env because
    #they are public, non-secret, and the same for every developer
    tx_ftp_host: str = "ftp.legis.state.tx.us"
    tx_ftp_timeout: int = 30
    #seconds between ftp requests, to stay a polite guest on a public server
    tx_ftp_delay: float = 1.0
    #89th regular session; lowercase works, the server is case-insensitive
    tx_session: str = "89r"


settings = Settings()