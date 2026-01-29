"""Google Cloud Storage client wrapper.

Provides a simplified interface for common GCS operations
including upload, download, and metadata management.
"""

import json
from pathlib import Path
from typing import Any

import structlog
from google.cloud import storage
from google.cloud.exceptions import NotFound

logger = structlog.get_logger(__name__)


class GCSClient:
    """Wrapper for Google Cloud Storage operations."""

    def __init__(self, bucket_name: str, project_id: str | None = None) -> None:
        """Initialize the GCS client.

        Args:
            bucket_name: Name of the GCS bucket to use.
            project_id: GCP project ID (uses default if None).
        """
        self.bucket_name = bucket_name
        self.project_id = project_id
        self._client: storage.Client | None = None
        self._bucket: storage.Bucket | None = None
        self.logger = logger.bind(component="gcs_client", bucket=bucket_name)

    @property
    def client(self) -> storage.Client:
        """Lazy-initialize the storage client."""
        if self._client is None:
            self._client = storage.Client(project=self.project_id)
        return self._client

    @property
    def bucket(self) -> storage.Bucket:
        """Get the configured bucket."""
        if self._bucket is None:
            self._bucket = self.client.bucket(self.bucket_name)
        return self._bucket

    def get_uri(self, blob_path: str) -> str:
        """Get the GCS URI for a blob path.

        Args:
            blob_path: Path within the bucket.

        Returns:
            Full GCS URI (gs://bucket/path).
        """
        return f"gs://{self.bucket_name}/{blob_path}"

    def upload_file(
        self,
        local_path: Path,
        blob_path: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload a local file to GCS.

        Args:
            local_path: Path to local file.
            blob_path: Destination path in bucket.
            content_type: MIME type (auto-detected if None).
            metadata: Custom metadata to attach.

        Returns:
            GCS URI of uploaded file.
        """
        blob = self.bucket.blob(blob_path)

        if metadata:
            blob.metadata = metadata

        self.logger.info("Uploading file", local=str(local_path), blob=blob_path)

        blob.upload_from_filename(str(local_path), content_type=content_type)

        return self.get_uri(blob_path)

    def upload_json(
        self,
        data: dict[str, Any] | list[Any],
        blob_path: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload JSON data to GCS.

        Args:
            data: JSON-serializable data.
            blob_path: Destination path in bucket.
            metadata: Custom metadata to attach.

        Returns:
            GCS URI of uploaded file.
        """
        blob = self.bucket.blob(blob_path)

        if metadata:
            blob.metadata = metadata

        self.logger.info("Uploading JSON", blob=blob_path)

        json_str = json.dumps(data, indent=2, default=str)
        blob.upload_from_string(json_str, content_type="application/json")

        return self.get_uri(blob_path)

    def download_file(self, blob_path: str, local_path: Path) -> Path:
        """Download a file from GCS.

        Args:
            blob_path: Path in bucket.
            local_path: Destination local path.

        Returns:
            Local path of downloaded file.

        Raises:
            NotFound: If blob doesn't exist.
        """
        blob = self.bucket.blob(blob_path)

        local_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger.info("Downloading file", blob=blob_path, local=str(local_path))

        blob.download_to_filename(str(local_path))

        return local_path

    def download_json(self, blob_path: str) -> dict[str, Any] | list[Any]:
        """Download and parse a JSON file from GCS.

        Args:
            blob_path: Path to JSON file in bucket.

        Returns:
            Parsed JSON data.

        Raises:
            NotFound: If blob doesn't exist.
        """
        blob = self.bucket.blob(blob_path)

        self.logger.info("Downloading JSON", blob=blob_path)

        content = blob.download_as_text()
        return json.loads(content)

    def exists(self, blob_path: str) -> bool:
        """Check if a blob exists.

        Args:
            blob_path: Path in bucket.

        Returns:
            True if blob exists.
        """
        blob = self.bucket.blob(blob_path)
        return blob.exists()

    def delete(self, blob_path: str) -> bool:
        """Delete a blob.

        Args:
            blob_path: Path in bucket.

        Returns:
            True if deleted, False if didn't exist.
        """
        blob = self.bucket.blob(blob_path)

        try:
            blob.delete()
            self.logger.info("Deleted blob", blob=blob_path)
            return True
        except NotFound:
            return False

    def list_blobs(
        self,
        prefix: str | None = None,
        delimiter: str | None = None,
        max_results: int | None = None,
    ) -> list[str]:
        """List blobs in the bucket.

        Args:
            prefix: Filter by path prefix.
            delimiter: Delimiter for hierarchy.
            max_results: Maximum number of results.

        Returns:
            List of blob paths.
        """
        blobs = self.client.list_blobs(
            self.bucket_name,
            prefix=prefix,
            delimiter=delimiter,
            max_results=max_results,
        )
        return [blob.name for blob in blobs]

    def create_bucket_if_not_exists(self, location: str = "us-central1") -> None:
        """Create the bucket if it doesn't exist.

        Args:
            location: GCS location for the bucket.
        """
        try:
            self.client.get_bucket(self.bucket_name)
            self.logger.info("Bucket already exists", bucket=self.bucket_name)
        except NotFound:
            bucket = self.client.create_bucket(self.bucket_name, location=location)
            self.logger.info("Created bucket", bucket=bucket.name, location=location)
