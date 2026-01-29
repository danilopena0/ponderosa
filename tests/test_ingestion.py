"""Tests for podcast ingestion module."""

import pytest

from ponderosa.ingestion.rss_parser import Episode, PodcastFeed, RSSParser


class TestRSSParser:
    """Tests for RSS feed parsing."""

    def test_parse_live_feed(self, sample_rss_feed_url: str) -> None:
        """Test parsing a real RSS feed."""
        parser = RSSParser(max_episodes=3)
        feed = parser.parse_feed(sample_rss_feed_url)

        assert isinstance(feed, PodcastFeed)
        assert feed.title == "Flirting with Models"
        assert len(feed.episodes) <= 3
        assert len(feed.episodes) > 0

    def test_episode_has_required_fields(self, sample_rss_feed_url: str) -> None:
        """Test that parsed episodes have all required fields."""
        parser = RSSParser(max_episodes=1)
        feed = parser.parse_feed(sample_rss_feed_url)

        episode = feed.episodes[0]

        assert episode.id is not None
        assert len(episode.id) == 12  # SHA256 hash prefix
        assert episode.title is not None
        assert episode.audio_url is not None
        assert str(episode.audio_url).startswith("http")

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

    def test_max_episodes_limit(self, sample_rss_feed_url: str) -> None:
        """Test that max_episodes limit is respected."""
        parser = RSSParser(max_episodes=2)
        feed = parser.parse_feed(sample_rss_feed_url)

        assert len(feed.episodes) <= 2

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

    def test_invalid_feed_url_raises(self) -> None:
        """Test that invalid feed URL raises ValueError."""
        parser = RSSParser()

        with pytest.raises(ValueError, match="Failed to parse"):
            parser.parse_feed("https://example.com/not-a-feed")


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
