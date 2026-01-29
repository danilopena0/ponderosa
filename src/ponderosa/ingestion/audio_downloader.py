"""Audio downloader for fetching podcast episodes and uploading to GCS.

Handles downloading audio files from URLs with retry logic,
progress tracking, and optional upload to Google Cloud Storage.
"""

import tempfile
from pathlib import Path

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ponderosa.ingestion.rss_parser import Episode, PodcastFeed
from ponderosa.storage.gcs_client import GCSClient

logger = structlog.get_logger(__name__)


class DownloadError(Exception):
    """Raised when audio download fails."""

    pass


class AudioDownloader:
    """Downloads podcast audio files and uploads to GCS."""

    def __init__(
        self,
        gcs_client: GCSClient | None = None,
        timeout_seconds: int = 300,
        chunk_size: int = 8192,
    ) -> None:
        """Initialize the audio downloader.

        Args:
            gcs_client: Optional GCS client for cloud uploads.
            timeout_seconds: HTTP request timeout.
            chunk_size: Chunk size for streaming downloads.
        """
        self.gcs_client = gcs_client
        self.timeout = timeout_seconds
        self.chunk_size = chunk_size
        self.logger = logger.bind(component="audio_downloader")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    def download_episode(
        self,
        episode: Episode,
        local_dir: Path | None = None,
        upload_to_gcs: bool = True,
        gcs_prefix: str = "audio",
    ) -> Path | str:
        """Download a single episode audio file.

        Args:
            episode: Episode to download.
            local_dir: Local directory for download (uses temp if None).
            upload_to_gcs: Whether to upload to GCS after download.
            gcs_prefix: GCS path prefix for uploads.

        Returns:
            Local path if not uploading, GCS URI if uploading.

        Raises:
            DownloadError: If download fails after retries.
        """
        self.logger.info(
            "Downloading episode",
            title=episode.title,
            url=str(episode.audio_url),
        )

        # Determine local path
        if local_dir:
            local_path = local_dir / episode.audio_filename
        else:
            local_path = Path(tempfile.gettempdir()) / episode.audio_filename

        try:
            self._download_file(str(episode.audio_url), local_path)
        except httpx.HTTPError as e:
            raise DownloadError(f"Failed to download {episode.audio_url}: {e}") from e

        self.logger.info(
            "Downloaded episode",
            title=episode.title,
            size_mb=round(local_path.stat().st_size / (1024 * 1024), 2),
        )

        # Upload to GCS if configured
        if upload_to_gcs and self.gcs_client:
            gcs_path = f"{gcs_prefix}/{episode.audio_filename}"
            gcs_uri = self.gcs_client.upload_file(local_path, gcs_path)

            # Clean up local file after upload
            local_path.unlink(missing_ok=True)

            self.logger.info("Uploaded to GCS", uri=gcs_uri)
            return gcs_uri

        return local_path

    def _download_file(self, url: str, dest_path: Path) -> None:
        """Stream download a file to disk.

        Args:
            url: URL to download from.
            dest_path: Destination file path.
        """
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()

                with open(dest_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=self.chunk_size):
                        f.write(chunk)

    def download_feed(
        self,
        feed: PodcastFeed,
        local_dir: Path | None = None,
        upload_to_gcs: bool = True,
        skip_existing: bool = True,
    ) -> dict[str, Path | str]:
        """Download all episodes from a podcast feed.

        Args:
            feed: Podcast feed with episodes to download.
            local_dir: Local directory for downloads.
            upload_to_gcs: Whether to upload to GCS.
            skip_existing: Skip episodes already in GCS.

        Returns:
            Dict mapping episode IDs to their paths/URIs.
        """
        self.logger.info(
            "Downloading feed",
            podcast=feed.title,
            episode_count=len(feed.episodes),
        )

        results: dict[str, Path | str] = {}
        gcs_prefix = f"audio/{feed.slug}"

        for episode in feed.episodes:
            # Check if already exists in GCS
            if skip_existing and upload_to_gcs and self.gcs_client:
                gcs_path = f"{gcs_prefix}/{episode.audio_filename}"
                if self.gcs_client.exists(gcs_path):
                    self.logger.info("Skipping existing episode", title=episode.title)
                    results[episode.id] = self.gcs_client.get_uri(gcs_path)
                    continue

            try:
                result = self.download_episode(
                    episode,
                    local_dir=local_dir,
                    upload_to_gcs=upload_to_gcs,
                    gcs_prefix=gcs_prefix,
                )
                results[episode.id] = result
            except DownloadError as e:
                self.logger.error("Failed to download episode", title=episode.title, error=str(e))
                # Continue with other episodes

        self.logger.info(
            "Feed download complete",
            podcast=feed.title,
            successful=len(results),
            total=len(feed.episodes),
        )

        return results

    def download_to_local(self, episode: Episode, dest_dir: Path) -> Path:
        """Download episode to local directory only (no GCS).

        Args:
            episode: Episode to download.
            dest_dir: Destination directory.

        Returns:
            Path to downloaded file.
        """
        return self.download_episode(
            episode, local_dir=dest_dir, upload_to_gcs=False
        )  # type: ignore
