from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "jobpilot-api"
    environment: str = "development"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    google_cloud_project: str = "jobpilot-local"
    firestore_project_id: str = "jobpilot-local"
    workflow_repository_mode: str = "memory"
    workflow_collection: str = "jobpilot-workflows"
    pubsub_mode: str = "memory"
    pubsub_project_id: str = "jobpilot-local"
    pubsub_topic: str = "jobpilot-workflows"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
