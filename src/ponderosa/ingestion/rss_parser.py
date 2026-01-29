"""RSS feed parser for podcast episode extraction.

Parses podcast RSS feeds and extracts episode metadata including
audio URLs, titles, descriptions, and publication dates.
"""

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import feedparser
import structlog
from pydantic import BaseModel, Field, HttpUrl, computed_field

logger = structlog.get_logger(__name__)


class Episode(BaseModel):
    """Represents a single podcast episode."""

    id: str = Field(description="Unique episode identifier (hash of guid or URL)")
    guid: str = Field(description="Original GUID from RSS feed")
    title: str = Field(description="Episode title")
    description: str = Field(default="", description="Episode description/show notes")
    audio_url: HttpUrl = Field(description="URL to audio file")
    audio_format: str = Field(default="mp3", description="Audio file format")
    audio_size_bytes: int | None = Field(default=None, description="Audio file size in bytes")
    duration_seconds: int | None = Field(default=None, description="Episode duration in seconds")
    published_at: datetime | None = Field(default=None, description="Publication date")
    season: int | None = Field(default=None, description="Season number if available")
    episode_number: int | None = Field(default=None, description="Episode number if available")
    image_url: HttpUrl | None = Field(default=None, description="Episode artwork URL")

    @computed_field
    @property
    def audio_filename(self) -> str:
        """Generate a clean filename for the audio file."""
        # Use episode ID + sanitized title
        safe_title = re.sub(r"[^a-zA-Z0-9]+", "_", self.title)[:50].strip("_").lower()
        return f"{self.id}_{safe_title}.{self.audio_format}"


class PodcastFeed(BaseModel):
    """Represents a podcast feed with metadata and episodes."""

    url: HttpUrl = Field(description="RSS feed URL")
    title: str = Field(description="Podcast title")
    description: str = Field(default="", description="Podcast description")
    author: str = Field(default="", description="Podcast author/host")
    image_url: HttpUrl | None = Field(default=None, description="Podcast artwork URL")
    website_url: HttpUrl | None = Field(default=None, description="Podcast website")
    language: str = Field(default="en", description="Podcast language")
    episodes: list[Episode] = Field(default_factory=list, description="List of episodes")
    last_fetched: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When feed was last fetched"
    )

    @computed_field
    @property
    def slug(self) -> str:
        """Generate a URL-safe slug for the podcast."""
        safe_name = re.sub(r"[^a-zA-Z0-9]+", "-", self.title)[:30].strip("-").lower()
        return safe_name or "podcast"


class RSSParser:
    """Parses podcast RSS feeds and extracts episode information."""

    def __init__(self, max_episodes: int = 10) -> None:
        """Initialize the RSS parser.

        Args:
            max_episodes: Maximum number of episodes to parse per feed.
        """
        self.max_episodes = max_episodes
        self.logger = logger.bind(component="rss_parser")

    def parse_feed(self, feed_url: str) -> PodcastFeed:
        """Parse an RSS feed and extract podcast information.

        Args:
            feed_url: URL of the RSS feed to parse.

        Returns:
            PodcastFeed: Parsed podcast with episodes.

        Raises:
            ValueError: If feed cannot be parsed or is empty.
        """
        self.logger.info("Parsing RSS feed", url=feed_url)

        feed = feedparser.parse(feed_url)

        if feed.bozo and not feed.entries:
            raise ValueError(f"Failed to parse feed: {feed.bozo_exception}")

        if not feed.entries:
            raise ValueError(f"Feed has no entries: {feed_url}")

        # Extract feed-level metadata
        feed_info = feed.feed
        podcast = PodcastFeed(
            url=feed_url,
            title=feed_info.get("title", "Unknown Podcast"),
            description=self._clean_html(feed_info.get("summary", feed_info.get("subtitle", ""))),
            author=feed_info.get("author", feed_info.get("itunes_author", "")),
            image_url=self._extract_image_url(feed_info),
            website_url=feed_info.get("link"),
            language=feed_info.get("language", "en"),
            episodes=[],
        )

        # Parse episodes
        for entry in feed.entries[: self.max_episodes]:
            episode = self._parse_episode(entry)
            if episode:
                podcast.episodes.append(episode)

        self.logger.info(
            "Parsed feed successfully",
            podcast=podcast.title,
            episode_count=len(podcast.episodes),
        )

        return podcast

    def _parse_episode(self, entry: dict[str, Any]) -> Episode | None:
        """Parse a single episode entry from the feed.

        Args:
            entry: Feed entry dictionary from feedparser.

        Returns:
            Episode if valid, None if missing required fields.
        """
        # Find audio enclosure
        audio_url = None
        audio_size = None
        audio_format = "mp3"

        for enclosure in entry.get("enclosures", []):
            if enclosure.get("type", "").startswith("audio/"):
                audio_url = enclosure.get("href") or enclosure.get("url")
                audio_size = int(enclosure.get("length", 0)) or None
                audio_format = self._detect_audio_format(enclosure.get("type", ""), audio_url)
                break

        # Fallback: check media:content
        if not audio_url:
            for media in entry.get("media_content", []):
                if media.get("type", "").startswith("audio/"):
                    audio_url = media.get("url")
                    break

        if not audio_url:
            self.logger.warning("Skipping episode without audio URL", title=entry.get("title"))
            return None

        # Generate stable episode ID from GUID or audio URL
        guid = entry.get("id") or entry.get("guid") or audio_url
        episode_id = self._generate_episode_id(guid)

        # Parse duration
        duration = self._parse_duration(entry.get("itunes_duration"))

        # Parse publication date
        published = None
        if entry.get("published_parsed"):
            try:
                published = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                pass

        # Extract episode/season numbers
        season = self._safe_int(entry.get("itunes_season"))
        episode_num = self._safe_int(entry.get("itunes_episode"))

        return Episode(
            id=episode_id,
            guid=guid,
            title=entry.get("title", "Untitled Episode"),
            description=self._clean_html(entry.get("summary", entry.get("description", ""))),
            audio_url=audio_url,
            audio_format=audio_format,
            audio_size_bytes=audio_size,
            duration_seconds=duration,
            published_at=published,
            season=season,
            episode_number=episode_num,
            image_url=entry.get("image", {}).get("href"),
        )

    def _generate_episode_id(self, guid: str) -> str:
        """Generate a stable, short ID from the GUID."""
        return hashlib.sha256(guid.encode()).hexdigest()[:12]

    def _detect_audio_format(self, mime_type: str, url: str | None) -> str:
        """Detect audio format from MIME type or URL."""
        mime_map = {
            "audio/mpeg": "mp3",
            "audio/mp3": "mp3",
            "audio/mp4": "m4a",
            "audio/x-m4a": "m4a",
            "audio/wav": "wav",
            "audio/flac": "flac",
            "audio/ogg": "ogg",
        }

        if mime_type in mime_map:
            return mime_map[mime_type]

        if url:
            path = urlparse(url).path.lower()
            for ext in ["mp3", "m4a", "wav", "flac", "ogg"]:
                if path.endswith(f".{ext}"):
                    return ext

        return "mp3"  # Default fallback

    def _parse_duration(self, duration_str: str | None) -> int | None:
        """Parse iTunes duration string to seconds."""
        if not duration_str:
            return None

        duration_str = str(duration_str).strip()

        # Try pure integer (seconds)
        if duration_str.isdigit():
            return int(duration_str)

        # Try HH:MM:SS or MM:SS format
        parts = duration_str.split(":")
        try:
            if len(parts) == 3:
                h, m, s = map(int, parts)
                return h * 3600 + m * 60 + s
            elif len(parts) == 2:
                m, s = map(int, parts)
                return m * 60 + s
        except ValueError:
            pass

        return None

    def _extract_image_url(self, feed_info: dict[str, Any]) -> str | None:
        """Extract podcast artwork URL from feed info."""
        # Try iTunes image first (usually higher quality)
        if feed_info.get("image", {}).get("href"):
            return feed_info["image"]["href"]

        # Fallback to standard image
        if feed_info.get("image", {}).get("url"):
            return feed_info["image"]["url"]

        return None

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        if not text:
            return ""
        # Simple HTML tag removal
        clean = re.sub(r"<[^>]+>", "", text)
        # Normalize whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def _safe_int(self, value: Any) -> int | None:
        """Safely convert value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
