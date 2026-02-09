"""Tests for CLI commands."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ponderosa.cli import cmd_download, cmd_list_bucket, cmd_parse_feed, main
from ponderosa.ingestion.rss_parser import Episode, PodcastFeed


def _make_feed(num_episodes: int = 2) -> PodcastFeed:
    """Create a fake PodcastFeed for testing."""
    episodes = [
        Episode(
            id=f"ep{i:010d}",
            guid=f"guid-{i}",
            title=f"Episode {i}",
            audio_url=f"https://example.com/ep{i}.mp3",
            audio_format="mp3",
            duration_seconds=3600 + i,
        )
        for i in range(num_episodes)
    ]
    return PodcastFeed(
        url="https://example.com/feed.xml",
        title="Test Podcast",
        author="Test Author",
        episodes=episodes,
    )


class TestMain:
    """Tests for the main CLI entry point."""

    def test_no_command_shows_help(self, capsys):
        """No subcommand should print help and return 1."""
        with patch("sys.argv", ["ponderosa"]):
            result = main()
        assert result == 1

    def test_unknown_command_exits(self):
        """Unknown subcommand should cause argparse to exit."""
        with patch("sys.argv", ["ponderosa", "unknown-cmd"]):
            with pytest.raises(SystemExit):
                main()


class TestParseFeed:
    """Tests for the parse-feed command."""

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.RSSParser")
    def test_basic_output(self, mock_parser_cls, _mock_logging, capsys):
        feed = _make_feed(2)
        mock_parser_cls.return_value.parse_feed.return_value = feed

        with patch("sys.argv", ["ponderosa", "parse-feed", "https://example.com/rss"]):
            result = main()

        assert result == 0
        output = capsys.readouterr().out
        assert "Test Podcast" in output
        assert "Test Author" in output
        assert "Episodes found: 2" in output
        assert "Episode 0" in output
        assert "Episode 1" in output

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.RSSParser")
    def test_max_episodes_passed(self, mock_parser_cls, _mock_logging):
        feed = _make_feed(1)
        mock_parser_cls.return_value.parse_feed.return_value = feed

        with patch("sys.argv", ["ponderosa", "parse-feed", "-n", "3", "https://example.com/rss"]):
            main()

        mock_parser_cls.assert_called_once_with(max_episodes=3)

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.RSSParser")
    def test_output_flag_writes_json(self, mock_parser_cls, _mock_logging, tmp_path):
        feed = _make_feed(1)
        mock_parser_cls.return_value.parse_feed.return_value = feed

        out_file = tmp_path / "feed.json"
        with patch("sys.argv", ["ponderosa", "parse-feed", "-o", str(out_file), "https://example.com/rss"]):
            result = main()

        assert result == 0
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["title"] == "Test Podcast"
        assert len(data["episodes"]) == 1

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.RSSParser")
    def test_duration_display(self, mock_parser_cls, _mock_logging, capsys):
        feed = _make_feed(1)
        feed.episodes[0].duration_seconds = 5400  # 90 minutes
        mock_parser_cls.return_value.parse_feed.return_value = feed

        with patch("sys.argv", ["ponderosa", "parse-feed", "https://example.com/rss"]):
            main()

        output = capsys.readouterr().out
        assert "90m" in output

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.RSSParser")
    def test_no_duration_shows_na(self, mock_parser_cls, _mock_logging, capsys):
        feed = _make_feed(1)
        feed.episodes[0].duration_seconds = None
        mock_parser_cls.return_value.parse_feed.return_value = feed

        with patch("sys.argv", ["ponderosa", "parse-feed", "https://example.com/rss"]):
            main()

        output = capsys.readouterr().out
        assert "N/A" in output


class TestDownload:
    """Tests for the download command."""

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.AudioDownloader")
    @patch("ponderosa.cli.RSSParser")
    @patch("ponderosa.cli.get_settings")
    def test_basic_download(self, mock_settings, mock_parser_cls, mock_dl_cls, _mock_logging, capsys, tmp_path):
        feed = _make_feed(1)
        mock_parser_cls.return_value.parse_feed.return_value = feed
        mock_dl_cls.return_value.download_feed.return_value = {"ep0000000000": tmp_path / "ep0.mp3"}

        with patch("sys.argv", ["ponderosa", "download", "https://example.com/rss"]):
            result = main()

        assert result == 0
        output = capsys.readouterr().out
        assert "Test Podcast" in output
        assert "Downloaded 1 episodes" in output

        # Verify download_feed called with skip_existing=True (default, no --force)
        call_kwargs = mock_dl_cls.return_value.download_feed.call_args
        assert call_kwargs.kwargs.get("skip_existing") is True or call_kwargs[1].get("skip_existing") is True

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.AudioDownloader")
    @patch("ponderosa.cli.RSSParser")
    @patch("ponderosa.cli.get_settings")
    def test_force_flag(self, mock_settings, mock_parser_cls, mock_dl_cls, _mock_logging, tmp_path):
        feed = _make_feed(1)
        mock_parser_cls.return_value.parse_feed.return_value = feed
        mock_dl_cls.return_value.download_feed.return_value = {}

        with patch("sys.argv", ["ponderosa", "download", "--force", "https://example.com/rss"]):
            main()

        call_kwargs = mock_dl_cls.return_value.download_feed.call_args
        assert call_kwargs.kwargs.get("skip_existing") is False or call_kwargs[1].get("skip_existing") is False

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.GCSClient")
    @patch("ponderosa.cli.AudioDownloader")
    @patch("ponderosa.cli.RSSParser")
    @patch("ponderosa.cli.get_settings")
    def test_upload_flag_creates_gcs_client(self, mock_settings, mock_parser_cls, mock_dl_cls, mock_gcs_cls, _mock_logging):
        feed = _make_feed(1)
        mock_parser_cls.return_value.parse_feed.return_value = feed
        mock_dl_cls.return_value.download_feed.return_value = {}
        mock_settings.return_value.gcp.bucket_name = "test-bucket"
        mock_settings.return_value.gcp.project_id = "test-project"

        with patch("sys.argv", ["ponderosa", "download", "--upload", "https://example.com/rss"]):
            main()

        mock_gcs_cls.assert_called_once_with(
            bucket_name="test-bucket",
            project_id="test-project",
        )

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.AudioDownloader")
    @patch("ponderosa.cli.RSSParser")
    @patch("ponderosa.cli.get_settings")
    def test_no_upload_without_bucket(self, mock_settings, mock_parser_cls, mock_dl_cls, _mock_logging):
        feed = _make_feed(1)
        mock_parser_cls.return_value.parse_feed.return_value = feed
        mock_dl_cls.return_value.download_feed.return_value = {}
        mock_settings.return_value.gcp.bucket_name = ""

        with patch("sys.argv", ["ponderosa", "download", "--upload", "https://example.com/rss"]):
            main()

        # AudioDownloader should be created with gcs_client=None
        mock_dl_cls.assert_called_once_with(gcs_client=None)

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.AudioDownloader")
    @patch("ponderosa.cli.RSSParser")
    @patch("ponderosa.cli.get_settings")
    def test_output_dir(self, mock_settings, mock_parser_cls, mock_dl_cls, _mock_logging, tmp_path):
        feed = _make_feed(1)
        mock_parser_cls.return_value.parse_feed.return_value = feed
        mock_dl_cls.return_value.download_feed.return_value = {}

        dest = tmp_path / "my_downloads"
        with patch("sys.argv", ["ponderosa", "download", "-o", str(dest), "https://example.com/rss"]):
            main()

        call_kwargs = mock_dl_cls.return_value.download_feed.call_args
        assert call_kwargs.kwargs.get("local_dir") == dest or call_kwargs[1].get("local_dir") == dest

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.AudioDownloader")
    @patch("ponderosa.cli.RSSParser")
    @patch("ponderosa.cli.get_settings")
    def test_max_episodes_passed(self, mock_settings, mock_parser_cls, mock_dl_cls, _mock_logging):
        feed = _make_feed(1)
        mock_parser_cls.return_value.parse_feed.return_value = feed
        mock_dl_cls.return_value.download_feed.return_value = {}

        with patch("sys.argv", ["ponderosa", "download", "-n", "7", "https://example.com/rss"]):
            main()

        mock_parser_cls.assert_called_once_with(max_episodes=7)


class TestListBucket:
    """Tests for the list-bucket command."""

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.GCSClient")
    @patch("ponderosa.cli.get_settings")
    def test_basic_list(self, mock_settings, mock_gcs_cls, _mock_logging, capsys):
        mock_settings.return_value.gcp.bucket_name = "my-bucket"
        mock_settings.return_value.gcp.project_id = "my-project"
        mock_gcs_cls.return_value.list_blobs.return_value = ["audio/ep1.mp3", "audio/ep2.mp3"]

        with patch("sys.argv", ["ponderosa", "list-bucket"]):
            result = main()

        assert result == 0
        output = capsys.readouterr().out
        assert "my-bucket" in output
        assert "audio/ep1.mp3" in output
        assert "audio/ep2.mp3" in output
        assert "Found 2 objects" in output

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.get_settings")
    def test_no_bucket_configured(self, mock_settings, _mock_logging, capsys):
        mock_settings.return_value.gcp.bucket_name = ""

        with patch("sys.argv", ["ponderosa", "list-bucket"]):
            result = main()

        assert result == 1
        output = capsys.readouterr().out
        assert "GCP_BUCKET_NAME not configured" in output

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.GCSClient")
    @patch("ponderosa.cli.get_settings")
    def test_prefix_filter(self, mock_settings, mock_gcs_cls, _mock_logging, capsys):
        mock_settings.return_value.gcp.bucket_name = "my-bucket"
        mock_settings.return_value.gcp.project_id = "my-project"
        mock_gcs_cls.return_value.list_blobs.return_value = ["audio/ep1.mp3"]

        with patch("sys.argv", ["ponderosa", "list-bucket", "--prefix", "audio/"]):
            main()

        mock_gcs_cls.return_value.list_blobs.assert_called_once_with(prefix="audio/", max_results=100)

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.GCSClient")
    @patch("ponderosa.cli.get_settings")
    def test_max_results(self, mock_settings, mock_gcs_cls, _mock_logging):
        mock_settings.return_value.gcp.bucket_name = "my-bucket"
        mock_settings.return_value.gcp.project_id = "my-project"
        mock_gcs_cls.return_value.list_blobs.return_value = []

        with patch("sys.argv", ["ponderosa", "list-bucket", "-n", "50"]):
            main()

        mock_gcs_cls.return_value.list_blobs.assert_called_once_with(prefix=None, max_results=50)

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.GCSClient")
    @patch("ponderosa.cli.get_settings")
    def test_empty_bucket(self, mock_settings, mock_gcs_cls, _mock_logging, capsys):
        mock_settings.return_value.gcp.bucket_name = "my-bucket"
        mock_settings.return_value.gcp.project_id = "my-project"
        mock_gcs_cls.return_value.list_blobs.return_value = []

        with patch("sys.argv", ["ponderosa", "list-bucket"]):
            result = main()

        assert result == 0
        output = capsys.readouterr().out
        assert "Found 0 objects" in output
