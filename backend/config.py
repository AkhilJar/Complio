from pydantic_settings import BaseSettings


#reads settings from environment variables (set by compose)
class Settings(BaseSettings):
    database_url: str
    #object storage — points at the minio container now, at s3/r2 after deploy
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str


settings = Settings()