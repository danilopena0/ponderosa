"""Central configuration management using pydantic-settings.

All configuration is loaded from environment variables with sensible defaults.
Create a .env file for local development (see .env.example).
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WhisperSettings(BaseSettings):
    """Whisper transcription configuration."""

    model_config = SettingsConfigDict(env_prefix="WHISPER_")

    model_size: str = Field(default="base", description="Whisper model size (tiny, base, small, medium, large-v3)")
    device: str = Field(default="cpu", description="Device to run on (cpu, cuda)")
    compute_type: str = Field(default="int8", description="Compute type (int8, float16, float32)")
    language: str = Field(default="en", description="Language code for transcription")


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
    whisper: WhisperSettings = Field(default_factory=WhisperSettings)
    podcast: PodcastSettings = Field(default_factory=PodcastSettings)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings: Application settings loaded from environment.
    """
    return Settings()
