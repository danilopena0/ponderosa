"""Tests for AudioDownloader."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import httpx
import pytest

# Mock google.cloud.storage before it gets imported by gcs_client
if "google.cloud.storage" not in sys.modules:
    sys.modules["google.cloud.storage"] = MagicMock()
if "google.cloud.exceptions" not in sys.modules:
    _mock_exceptions = MagicMock()
    _mock_exceptions.NotFound = type("NotFound", (Exception,), {})
    sys.modules["google.cloud.exceptions"] = _mock_exceptions

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
def mock_gcs() -> MagicMock:
    """A mock GCSClient."""
    gcs = MagicMock()
    gcs.upload_file.return_value = "gs://bucket/audio/abc123def456_test_episode_one.mp3"
    gcs.get_uri.side_effect = lambda path: f"gs://bucket/{path}"
    gcs.exists.return_value = False
    return gcs


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
        assert dl.gcs_client is None
        assert dl.timeout == 300
        assert dl.chunk_size == 8192

    def test_custom_params(self, mock_gcs):
        dl = AudioDownloader(gcs_client=mock_gcs, timeout_seconds=60, chunk_size=4096)
        assert dl.gcs_client is mock_gcs
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
        result = dl.download_episode(episode, local_dir=tmp_path, upload_to_gcs=False)

        assert isinstance(result, Path)
        assert result.parent == tmp_path
        assert result.name == episode.audio_filename
        # File should exist with the fake audio content
        assert result.read_bytes() == b"fake-audio-chunk-1fake-audio-chunk-2"

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_download_uses_tempdir_when_no_local_dir(self, mock_httpx_client, episode):
        """When local_dir is None, uses system temp directory."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader()
        result = dl.download_episode(episode, local_dir=None, upload_to_gcs=False)

        assert isinstance(result, Path)
        # Clean up the temp file
        result.unlink(missing_ok=True)

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_upload_to_gcs_returns_uri(self, mock_httpx_client, episode, mock_gcs, tmp_path):
        """When upload_to_gcs=True and gcs_client set, uploads and returns GCS URI."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader(gcs_client=mock_gcs)
        result = dl.download_episode(episode, local_dir=tmp_path, upload_to_gcs=True, gcs_prefix="audio")

        assert isinstance(result, str)
        assert result.startswith("gs://")
        mock_gcs.upload_file.assert_called_once()
        call_args = mock_gcs.upload_file.call_args
        assert call_args[0][1] == f"audio/{episode.audio_filename}"

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_upload_cleans_up_local_file(self, mock_httpx_client, episode, mock_gcs, tmp_path):
        """After GCS upload, local file should be deleted."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader(gcs_client=mock_gcs)
        dl.download_episode(episode, local_dir=tmp_path, upload_to_gcs=True)

        local_file = tmp_path / episode.audio_filename
        assert not local_file.exists()

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_no_upload_when_gcs_client_is_none(self, mock_httpx_client, episode, tmp_path):
        """When gcs_client is None, upload_to_gcs=True should still return local path."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader(gcs_client=None)
        result = dl.download_episode(episode, local_dir=tmp_path, upload_to_gcs=True)

        assert isinstance(result, Path)

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
        # The retry decorator will retry 3 times, then the outer except catches HTTPError
        # and raises DownloadError
        with pytest.raises(DownloadError, match="Failed to download"):
            dl.download_episode(episode, local_dir=tmp_path, upload_to_gcs=False)


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
        # Check iter_bytes was called with configured chunk_size
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
        results = dl.download_feed(feed, local_dir=tmp_path, upload_to_gcs=False)

        assert len(results) == 2
        assert feed.episodes[0].id in results
        assert feed.episodes[1].id in results

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_skip_existing_in_gcs(self, mock_httpx_client, feed, mock_gcs, tmp_path):
        """When skip_existing=True and episode exists in GCS, skip the download."""
        # First episode exists, second doesn't
        mock_gcs.exists.side_effect = [True, False]

        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader(gcs_client=mock_gcs)
        results = dl.download_feed(feed, local_dir=tmp_path, upload_to_gcs=True, skip_existing=True)

        assert len(results) == 2
        # First episode should use get_uri (skipped), second should be downloaded
        mock_gcs.get_uri.assert_called_once()
        mock_gcs.upload_file.assert_called_once()

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_skip_existing_false_downloads_all(self, mock_httpx_client, feed, mock_gcs, tmp_path):
        """When skip_existing=False, downloads even if file exists in GCS."""
        mock_gcs.exists.return_value = True

        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader(gcs_client=mock_gcs)
        results = dl.download_feed(feed, local_dir=tmp_path, upload_to_gcs=True, skip_existing=False)

        assert len(results) == 2
        # exists() should never be called
        mock_gcs.exists.assert_not_called()

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_continues_on_download_error(self, mock_httpx_client, feed, tmp_path):
        """If one episode fails, continues with the rest."""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First episode fails (HTTPError -> caught -> DownloadError)
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
        results = dl.download_feed(feed, local_dir=tmp_path, upload_to_gcs=False)

        # Only second episode should succeed
        assert len(results) == 1
        assert feed.episodes[1].id in results

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_gcs_prefix_uses_feed_slug(self, mock_httpx_client, feed, mock_gcs, tmp_path):
        """download_feed uses audio/{feed.slug} as the GCS prefix."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader(gcs_client=mock_gcs)
        dl.download_feed(feed, local_dir=tmp_path, upload_to_gcs=True, skip_existing=False)

        # Check upload paths include the feed slug
        for call in mock_gcs.upload_file.call_args_list:
            gcs_path = call[0][1]
            assert gcs_path.startswith(f"audio/{feed.slug}/")

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_no_gcs_skip_check_without_client(self, mock_httpx_client, feed, tmp_path):
        """Without a GCS client, skip_existing logic is bypassed."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader(gcs_client=None)
        results = dl.download_feed(feed, local_dir=tmp_path, upload_to_gcs=True, skip_existing=True)

        assert len(results) == 2


class TestDownloadToLocal:
    """Tests for download_to_local convenience method."""

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_returns_local_path(self, mock_httpx_client, episode, tmp_path):
        """download_to_local returns a Path, never a GCS URI."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader()
        result = dl.download_to_local(episode, tmp_path)

        assert isinstance(result, Path)
        assert result.parent == tmp_path
        assert result.exists()

    @patch("ponderosa.ingestion.audio_downloader.httpx.Client")
    def test_does_not_upload_to_gcs(self, mock_httpx_client, episode, mock_gcs, tmp_path):
        """download_to_local never uploads even with gcs_client set."""
        stream_cm = _make_mock_response()
        mock_httpx_client.return_value = _make_mock_client(stream_cm)

        dl = AudioDownloader(gcs_client=mock_gcs)
        dl.download_to_local(episode, tmp_path)

        mock_gcs.upload_file.assert_not_called()


class TestDownloadError:
    """Tests for DownloadError exception."""

    def test_is_exception(self):
        assert issubclass(DownloadError, Exception)

    def test_message(self):
        err = DownloadError("something broke")
        assert str(err) == "something broke"
