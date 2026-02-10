"""Tests for AudioDownloader."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from ponderosa.ingestion.audio_downloader import AudioDownloader, DownloadError
from ponderosa.ingestion.rss_parser import Episode, PodcastFeed


@pytest.fixture
def episode() -> Episode:
    """A sample episode for testing."""
    return Episode(
        id="abc123def456",
        guid="test-guid-001",
        title="Test Episode One",
        audio_url="https://example.com/ep1.mp3",
        audio_format="mp3",
        duration_seconds=1800,
    )


@pytest.fixture
def episode_b() -> Episode:
    """A second sample episode."""
    return Episode(
        id="xyz789uvw012",
        guid="test-guid-002",
        title="Test Episode Two",
        audio_url="https://example.com/ep2.mp3",
        audio_format="mp3",
    )


@pytest.fixture
def feed(episode, episode_b) -> PodcastFeed:
    """A sample podcast feed with two episodes."""
    return PodcastFeed(
        url="https://example.com/feed.xml",
        title="Test Podcast",
        episodes=[episode, episode_b],
    )


def _make_mock_response(chunks: list[bytes] | None = None):
    """Create a mock streaming response context manager."""
    if chunks is None:
        chunks = [b"fake-audio-chunk-1", b"fake-audio-chunk-2"]

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.iter_bytes.return_value = iter(chunks)

    stream_cm = MagicMock()
    stream_cm.__enter__ = MagicMock(return_value=response)
    stream_cm.__exit__ = MagicMock(return_value=False)
    return stream_cm


def _make_mock_client(stream_cm):
    """Create a mock httpx.Client context manager."""
    mock_client = MagicMock()
    mock_client.stream.return_value = stream_cm
    client_cm = MagicMock()
    client_cm.__enter__ = MagicMock(return_value=mock_client)
    client_cm.__exit__ = MagicMock(return_value=False)
    return client_cm


class TestAudioDownloaderInit:
    """Tests for AudioDownloader initialization."""

    def test_defaults(self):
        dl = AudioDownloader()
        assert dl.timeout == 300
        assert dl.chunk_size == 8192

    def test_custom_params(self):
        dl = AudioDownloader(timeout_seconds=60, chunk_size=4096)
        assert dl.timeout == 60
        assert dl.chunk_size == 4096


class TestDownloadEpisode:
    """Tests for download_episode method."""

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_download_to_local_dir(self, mock_httpx_client, episode, tmp_path):
        """Download writes audio bytes to the specified local dir."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader()
        result = dl.download_episode(episode, local_dir=tmp_path)

        assert isinstance(result, Path)
        assert result.parent == tmp_path
        assert result.name == episode.audio_filename
        assert result.read_bytes() == b"fake-audio-chunk-1fake-audio-chunk-2"

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_download_uses_tempdir_when_no_local_dir(self, mock_httpx_client, episode):
        """When local_dir is None, uses system temp directory."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader()
        result = dl.download_episode(episode, local_dir=None)

        assert isinstance(result, Path)
        result.unlink(missing_ok=True)

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_download_error_on_http_failure(self, mock_httpx_client, episode, tmp_path):
        """HTTPError from httpx raises DownloadError after retries exhaust."""
        mock_client = MagicMock()
        mock_client.stream.side_effect = httpx.HTTPError("connection failed")
        client_cm = MagicMock()
        client_cm.__enter__ = MagicMock(return_value=mock_client)
        client_cm.__exit__ = MagicMock(return_value=False)
        mock_httpx_client.return_value = client_cm

        dl = AudioDownloader()
        with pytest.raises(DownloadError, match="Failed to download"):
            dl.download_episode(episode, local_dir=tmp_path)


class TestDownloadFile:
    """Tests for the _download_file internal method."""

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_creates_parent_dirs(self, mock_httpx_client, tmp_path):
        """_download_file creates parent directories if needed."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader()
        dest = tmp_path / "sub" / "dir" / "file.mp3"
        dl._download_file("https://example.com/file.mp3", dest)

        assert dest.exists()
        assert dest.read_bytes() == b"fake-audio-chunk-1fake-audio-chunk-2"

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_uses_configured_timeout_and_chunk_size(self, mock_httpx_client, tmp_path):
        """Verifies timeout and chunk_size are passed through."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader(timeout_seconds=60, chunk_size=1024)
        dest = tmp_path / "file.mp3"
        dl._download_file("https://example.com/file.mp3", dest)

        mock_httpx_client.assert_called_once_with(timeout=60, follow_redirects=True)
        response = stream_cm.__enter__.return_value
        response.iter_bytes.assert_called_once_with(chunk_size=1024)


class TestDownloadFeed:
    """Tests for download_feed method."""

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_downloads_all_episodes(self, mock_httpx_client, feed, tmp_path):
        """download_feed downloads each episode in the feed."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader()
        results = dl.download_feed(feed, local_dir=tmp_path)

        assert len(results) == 2
        assert feed.episodes[0].id in results
        assert feed.episodes[1].id in results

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_skip_existing_local(self, mock_httpx_client, feed, tmp_path):
        """When skip_existing=True and file exists locally, skip the download."""
        # Create the first episode's file locally
        local_file = tmp_path / feed.episodes[0].audio_filename
        local_file.write_bytes(b"existing")

        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader()
        results = dl.download_feed(feed, local_dir=tmp_path, skip_existing=True)

        assert len(results) == 2
        # First episode should be skipped (kept existing), second downloaded
        assert results[feed.episodes[0].id] == local_file

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_continues_on_download_error(self, mock_httpx_client, feed, tmp_path):
        """If one episode fails, continues with the rest."""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_client = MagicMock()
                mock_client.stream.side_effect = httpx.HTTPError("fail")
                cm = MagicMock()
                cm.__enter__ = MagicMock(return_value=mock_client)
                cm.__exit__ = MagicMock(return_value=False)
                return cm
            else:
                return _make_mock_client(_make_mock_response())

        mock_httpx_client.side_effect = side_effect

        dl = AudioDownloader()
        results = dl.download_feed(feed, local_dir=tmp_path)

        assert len(results) == 1
        assert feed.episodes[1].id in results


class TestDownloadToLocal:
    """Tests for download_to_local convenience method."""

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_returns_local_path(self, mock_httpx_client, episode, tmp_path):
        """download_to_local returns a Path."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader()
        result = dl.download_to_local(episode, tmp_path)

        assert isinstance(result, Path)
        assert result.parent == tmp_path
        assert result.exists()


class TestDownloadError:
    """Tests for DownloadError exception."""

    def test_is_exception(self):
        assert issubclass(DownloadError, Exception)

    def test_message(self):
        err = DownloadError("something broke")
        assert str(err) == "something broke"
