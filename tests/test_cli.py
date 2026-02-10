"""Tests for CLI commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ponderosa.cli import cmd_download, cmd_parse_feed, cmd_transcribe, main
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
    def test_basic_download(self, mock_parser_cls, mock_dl_cls, _mock_logging, capsys, tmp_path):
        feed = _make_feed(1)
        mock_parser_cls.return_value.parse_feed.return_value = feed
        mock_dl_cls.return_value.download_feed.return_value = {"ep0000000000": tmp_path / "ep0.mp3"}

        with patch("sys.argv", ["ponderosa", "download", "https://example.com/rss"]):
            result = main()

        assert result == 0
        output = capsys.readouterr().out
        assert "Test Podcast" in output
        assert "Downloaded 1 episodes" in output

        call_kwargs = mock_dl_cls.return_value.download_feed.call_args
        assert call_kwargs.kwargs.get("skip_existing") is True or call_kwargs[1].get("skip_existing") is True

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.AudioDownloader")
    @patch("ponderosa.cli.RSSParser")
    def test_force_flag(self, mock_parser_cls, mock_dl_cls, _mock_logging, tmp_path):
        feed = _make_feed(1)
        mock_parser_cls.return_value.parse_feed.return_value = feed
        mock_dl_cls.return_value.download_feed.return_value = {}

        with patch("sys.argv", ["ponderosa", "download", "--force", "https://example.com/rss"]):
            main()

        call_kwargs = mock_dl_cls.return_value.download_feed.call_args
        assert call_kwargs.kwargs.get("skip_existing") is False or call_kwargs[1].get("skip_existing") is False

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.AudioDownloader")
    @patch("ponderosa.cli.RSSParser")
    def test_output_dir(self, mock_parser_cls, mock_dl_cls, _mock_logging, tmp_path):
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
    def test_max_episodes_passed(self, mock_parser_cls, mock_dl_cls, _mock_logging):
        feed = _make_feed(1)
        mock_parser_cls.return_value.parse_feed.return_value = feed
        mock_dl_cls.return_value.download_feed.return_value = {}

        with patch("sys.argv", ["ponderosa", "download", "-n", "7", "https://example.com/rss"]):
            main()

        mock_parser_cls.assert_called_once_with(max_episodes=7)


class TestTranscribe:
    """Tests for the transcribe command."""

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.get_settings")
    def test_file_not_found(self, mock_settings, _mock_logging, capsys):
        mock_settings.return_value.whisper.model_size = "base"

        with patch("sys.argv", ["ponderosa", "transcribe", "/nonexistent/audio.mp3"]):
            result = main()

        assert result == 1
        output = capsys.readouterr().out
        assert "File not found" in output

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.get_settings")
    @patch("faster_whisper.WhisperModel")
    def test_basic_transcribe(self, mock_whisper_cls, mock_settings, _mock_logging, tmp_path, capsys):
        mock_settings.return_value.whisper.model_size = "base"
        mock_settings.return_value.whisper.device = "cpu"
        mock_settings.return_value.whisper.compute_type = "int8"
        mock_settings.return_value.whisper.language = "en"

        # Create a fake audio file
        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio data")

        # Mock the whisper model
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 5.0
        mock_segment.text = " Hello world"

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.duration = 5.0

        mock_whisper_cls.return_value.transcribe.return_value = (iter([mock_segment]), mock_info)

        with patch("sys.argv", ["ponderosa", "transcribe", str(audio_file)]):
            result = main()

        assert result == 0

        # Check transcript JSON was created
        transcript_file = audio_file.with_suffix(".transcript.json")
        assert transcript_file.exists()
        data = json.loads(transcript_file.read_text())
        assert data["text"] == "Hello world"
        assert data["language"] == "en"
        assert len(data["segments"]) == 1

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.get_settings")
    @patch("faster_whisper.WhisperModel")
    def test_custom_output_path(self, mock_whisper_cls, mock_settings, _mock_logging, tmp_path):
        mock_settings.return_value.whisper.model_size = "base"
        mock_settings.return_value.whisper.device = "cpu"
        mock_settings.return_value.whisper.compute_type = "int8"
        mock_settings.return_value.whisper.language = "en"

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio data")
        output_file = tmp_path / "custom_output.json"

        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 3.0
        mock_segment.text = " Test"

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.duration = 3.0

        mock_whisper_cls.return_value.transcribe.return_value = (iter([mock_segment]), mock_info)

        with patch("sys.argv", ["ponderosa", "transcribe", "-o", str(output_file), str(audio_file)]):
            result = main()

        assert result == 0
        assert output_file.exists()

    @patch("ponderosa.cli.setup_logging")
    @patch("ponderosa.cli.get_settings")
    @patch("faster_whisper.WhisperModel")
    def test_model_flag(self, mock_whisper_cls, mock_settings, _mock_logging, tmp_path, capsys):
        mock_settings.return_value.whisper.model_size = "base"
        mock_settings.return_value.whisper.device = "cpu"
        mock_settings.return_value.whisper.compute_type = "int8"
        mock_settings.return_value.whisper.language = "en"

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio data")

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.duration = 1.0

        mock_whisper_cls.return_value.transcribe.return_value = (iter([]), mock_info)

        with patch("sys.argv", ["ponderosa", "transcribe", "-m", "large-v3", str(audio_file)]):
            main()

        output = capsys.readouterr().out
        assert "large-v3" in output
