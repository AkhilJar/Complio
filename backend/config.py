from pydantic_settings import BaseSettings


#reads settings from environment variables (set by compose)
class Settings(BaseSettings):
    database_url: str


settings = Settings()