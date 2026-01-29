"""Central configuration management using pydantic-settings.

All configuration is loaded from environment variables with sensible defaults.
Create a .env file for local development (see .env.example).
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GCPSettings(BaseSettings):
    """Google Cloud Platform configuration."""

    model_config = SettingsConfigDict(env_prefix="GCP_")

    project_id: str = Field(description="GCP project ID")
    region: str = Field(default="us-central1", description="GCP region for resources")
    bucket_name: str = Field(description="GCS bucket for audio and transcripts")


class SpeechSettings(BaseSettings):
    """Speech-to-Text API configuration."""

    model_config = SettingsConfigDict(env_prefix="SPEECH_")

    model: str = Field(default="chirp", description="STT model (chirp for best quality)")
    language_code: str = Field(default="en-US", description="Primary language")
    enable_diarization: bool = Field(default=True, description="Enable speaker diarization")
    min_speakers: int = Field(default=1, description="Minimum expected speakers")
    max_speakers: int = Field(default=4, description="Maximum expected speakers")


class GeminiSettings(BaseSettings):
    """Gemini API configuration for enrichment."""

    model_config = SettingsConfigDict(env_prefix="GEMINI_")

    model: str = Field(default="gemini-1.5-flash", description="Gemini model for enrichment")
    max_output_tokens: int = Field(default=2048, description="Max tokens in response")
    temperature: float = Field(default=0.3, description="Generation temperature")


class PipelineSettings(BaseSettings):
    """Vertex AI Pipeline configuration."""

    model_config = SettingsConfigDict(env_prefix="PIPELINE_")

    service_account: str | None = Field(default=None, description="Service account for pipeline")
    machine_type: str = Field(default="e2-standard-4", description="Machine type for components")
    max_concurrent_episodes: int = Field(default=5, description="Max episodes to process in parallel")


class PodcastSettings(BaseSettings):
    """Podcast ingestion configuration."""

    model_config = SettingsConfigDict(env_prefix="PODCAST_")

    default_rss_feeds: list[str] = Field(
        default=["https://flirtingwithmodels.libsyn.com/rss"],
        description="Default RSS feeds to ingest",
    )
    max_episodes_per_feed: int = Field(default=10, description="Max episodes to fetch per feed")
    audio_format: Literal["mp3", "wav", "flac"] = Field(
        default="mp3", description="Preferred audio format"
    )
    skip_existing: bool = Field(default=True, description="Skip already downloaded episodes")


class Settings(BaseSettings):
    """Main application settings aggregating all config sections."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "staging", "production"] = Field(
        default="development", description="Deployment environment"
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Logging level"
    )

    # Sub-configurations
    gcp: GCPSettings = Field(default_factory=GCPSettings)
    speech: SpeechSettings = Field(default_factory=SpeechSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    podcast: PodcastSettings = Field(default_factory=PodcastSettings)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings: Application settings loaded from environment.
    """
    return Settings()
