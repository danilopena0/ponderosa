"""Tests for podcast ingestion module."""

import pytest

from ponderosa.ingestion.rss_parser import Episode, PodcastFeed, RSSParser


class TestRSSParser:
    """Tests for RSS feed parsing."""

    def test_episode_audio_filename_generation(self) -> None:
        """Test audio filename generation."""
        episode = Episode(
            id="abc123def456",
            guid="test-guid",
            title="My Great Episode: Part 1!",
            audio_url="https://example.com/audio.mp3",
            audio_format="mp3",
        )

        filename = episode.audio_filename
        assert filename.startswith("abc123def456_")
        assert filename.endswith(".mp3")
        assert ":" not in filename  # Special chars removed
        assert "!" not in filename

    def test_podcast_slug_generation(self) -> None:
        """Test podcast slug generation."""
        feed = PodcastFeed(
            url="https://example.com/feed.xml",
            title="The Best Podcast Ever!",
        )

        assert feed.slug == "the-best-podcast-ever"

    def test_duration_parsing(self) -> None:
        """Test duration string parsing."""
        parser = RSSParser()

        # HH:MM:SS format
        assert parser._parse_duration("1:30:45") == 5445

        # MM:SS format
        assert parser._parse_duration("45:30") == 2730

        # Pure seconds
        assert parser._parse_duration("3600") == 3600

        # None handling
        assert parser._parse_duration(None) is None
        assert parser._parse_duration("") is None

class TestEpisodeModel:
    """Tests for Episode Pydantic model."""

    def test_episode_serialization(self, sample_episode_data: dict) -> None:
        """Test episode can be serialized to dict."""
        episode = Episode(**sample_episode_data)
        data = episode.model_dump()

        assert data["id"] == sample_episode_data["id"]
        assert data["title"] == sample_episode_data["title"]
        assert "audio_filename" in data  # Computed field

    def test_episode_json_serialization(self, sample_episode_data: dict) -> None:
        """Test episode can be serialized to JSON."""
        episode = Episode(**sample_episode_data)
        json_str = episode.model_dump_json()

        assert sample_episode_data["title"] in json_str
