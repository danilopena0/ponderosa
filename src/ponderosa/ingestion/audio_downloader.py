"""Audio downloader for fetching podcast episodes.

Handles downloading audio files from URLs with retry logic
and progress tracking.
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

logger = structlog.get_logger(__name__)


class DownloadError(Exception):
    """Raised when audio download fails."""

    pass


class AudioDownloader:
    """Downloads podcast audio files to local storage."""

    def __init__(
        self,
        timeout_seconds: int = 300,
        chunk_size: int = 8192,
    ) -> None:
        """Initialize the audio downloader.

        Args:
            timeout_seconds: HTTP request timeout.
            chunk_size: Chunk size for streaming downloads.
        """
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
    ) -> Path:
        """Download a single episode audio file.

        Args:
            episode: Episode to download.
            local_dir: Local directory for download (uses temp if None).

        Returns:
            Local path to downloaded file.

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
        skip_existing: bool = True,
    ) -> dict[str, Path]:
        """Download all episodes from a podcast feed.

        Args:
            feed: Podcast feed with episodes to download.
            local_dir: Local directory for downloads.
            skip_existing: Skip episodes already downloaded locally.

        Returns:
            Dict mapping episode IDs to their local paths.
        """
        self.logger.info(
            "Downloading feed",
            podcast=feed.title,
            episode_count=len(feed.episodes),
        )

        results: dict[str, Path] = {}

        for episode in feed.episodes:
            # Check if already exists locally
            if skip_existing and local_dir:
                local_path = local_dir / episode.audio_filename
                if local_path.exists():
                    self.logger.info("Skipping existing episode", title=episode.title)
                    results[episode.id] = local_path
                    continue

            try:
                result = self.download_episode(episode, local_dir=local_dir)
                results[episode.id] = result
            except DownloadError as e:
                self.logger.error("Failed to download episode", title=episode.title, error=str(e))

        self.logger.info(
            "Feed download complete",
            podcast=feed.title,
            successful=len(results),
            total=len(feed.episodes),
        )

        return results
