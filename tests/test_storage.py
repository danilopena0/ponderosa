"""Tests for GCS storage client."""

import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# Mock google.cloud.storage and google.cloud.exceptions before importing gcs_client,
# because the rsa package (transitive dep) is broken on Python 3.13.
_mock_storage_module = MagicMock()
_mock_exceptions_module = ModuleType("google.cloud.exceptions")


class _NotFound(Exception):
    """Stand-in for google.cloud.exceptions.NotFound."""

    def __init__(self, message="not found"):
        super().__init__(message)


_mock_exceptions_module.NotFound = _NotFound  # type: ignore[attr-defined]

# Patch sys.modules so that `from google.cloud import storage` and
# `from google.cloud.exceptions import NotFound` resolve to our mocks.
sys.modules.setdefault("google.cloud.storage", _mock_storage_module)
sys.modules.setdefault("google.cloud.exceptions", _mock_exceptions_module)

# Also ensure parent packages exist as modules in sys.modules
for _pkg in ("google", "google.cloud"):
    if _pkg not in sys.modules:
        sys.modules[_pkg] = ModuleType(_pkg)

# Now we can safely import the module under test
from ponderosa.storage.gcs_client import GCSClient  # noqa: E402

BUCKET_NAME = "test-bucket"
PROJECT_ID = "test-project"


@pytest.fixture
def mock_storage_client():
    """Create a mock google.cloud.storage.Client."""
    with patch("ponderosa.storage.gcs_client.storage.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        yield mock_client


@pytest.fixture
def gcs(mock_storage_client):
    """Create a GCSClient with mocked storage backend."""
    client = GCSClient(bucket_name=BUCKET_NAME, project_id=PROJECT_ID)
    return client


class TestLazyInitialization:
    """Tests for lazy client/bucket initialization."""

    def test_client_not_created_on_init(self):
        """Client should not be created until first access."""
        with patch("ponderosa.storage.gcs_client.storage.Client") as mock_cls:
            gcs = GCSClient(bucket_name=BUCKET_NAME)
            mock_cls.assert_not_called()

    def test_client_created_on_first_access(self, mock_storage_client):
        """Client should be created on first property access."""
        gcs = GCSClient(bucket_name=BUCKET_NAME, project_id=PROJECT_ID)
        _ = gcs.client
        assert gcs._client is mock_storage_client

    def test_client_reused_on_subsequent_access(self, mock_storage_client):
        """Client should be reused after first creation."""
        gcs = GCSClient(bucket_name=BUCKET_NAME, project_id=PROJECT_ID)
        c1 = gcs.client
        c2 = gcs.client
        assert c1 is c2

    def test_bucket_created_on_first_access(self, gcs, mock_storage_client):
        """Bucket should be lazily retrieved."""
        mock_bucket = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        _ = gcs.bucket
        mock_storage_client.bucket.assert_called_once_with(BUCKET_NAME)

    def test_bucket_reused_on_subsequent_access(self, gcs, mock_storage_client):
        """Bucket should be reused after first retrieval."""
        mock_bucket = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        b1 = gcs.bucket
        b2 = gcs.bucket
        assert b1 is b2
        mock_storage_client.bucket.assert_called_once()


class TestGetUri:
    """Tests for get_uri method."""

    def test_get_uri_format(self):
        """Should return gs://bucket/path format."""
        gcs = GCSClient(bucket_name=BUCKET_NAME)
        assert gcs.get_uri("path/to/file.json") == f"gs://{BUCKET_NAME}/path/to/file.json"

    def test_get_uri_no_leading_slash(self):
        """Should handle paths without leading slash."""
        gcs = GCSClient(bucket_name=BUCKET_NAME)
        assert gcs.get_uri("file.txt") == f"gs://{BUCKET_NAME}/file.txt"


class TestUploadFile:
    """Tests for upload_file method."""

    def test_upload_file_basic(self, gcs, mock_storage_client):
        """Should upload file and return URI."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        result = gcs.upload_file(Path("/tmp/test.mp3"), "audio/test.mp3")

        mock_bucket.blob.assert_called_once_with("audio/test.mp3")
        mock_blob.upload_from_filename.assert_called_once_with(
            "/tmp/test.mp3", content_type=None
        )
        assert result == f"gs://{BUCKET_NAME}/audio/test.mp3"

    def test_upload_file_with_content_type(self, gcs, mock_storage_client):
        """Should pass content_type to upload."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        gcs.upload_file(
            Path("/tmp/test.mp3"), "audio/test.mp3", content_type="audio/mpeg"
        )

        mock_blob.upload_from_filename.assert_called_once_with(
            "/tmp/test.mp3", content_type="audio/mpeg"
        )

    def test_upload_file_with_metadata(self, gcs, mock_storage_client):
        """Should set metadata on blob before upload."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        metadata = {"episode_id": "abc123", "podcast": "test"}
        gcs.upload_file(Path("/tmp/test.mp3"), "audio/test.mp3", metadata=metadata)

        assert mock_blob.metadata == metadata

    def test_upload_file_no_metadata(self, gcs, mock_storage_client):
        """Should not set metadata when None."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock(spec=["upload_from_filename", "metadata"])
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        # Start with metadata unset
        mock_blob.metadata = None

        gcs.upload_file(Path("/tmp/test.mp3"), "audio/test.mp3")

        # metadata should still be None since no metadata was passed
        assert mock_blob.metadata is None


class TestUploadJson:
    """Tests for upload_json method."""

    def test_upload_json_dict(self, gcs, mock_storage_client):
        """Should serialize dict and upload as JSON."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        data = {"key": "value", "count": 42}
        result = gcs.upload_json(data, "data/output.json")

        mock_blob.upload_from_string.assert_called_once()
        call_args = mock_blob.upload_from_string.call_args
        uploaded_str = call_args[0][0]
        assert json.loads(uploaded_str) == data
        assert call_args[1]["content_type"] == "application/json"
        assert result == f"gs://{BUCKET_NAME}/data/output.json"

    def test_upload_json_list(self, gcs, mock_storage_client):
        """Should handle list data."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        data = [{"id": 1}, {"id": 2}]
        gcs.upload_json(data, "data/list.json")

        uploaded_str = mock_blob.upload_from_string.call_args[0][0]
        assert json.loads(uploaded_str) == data

    def test_upload_json_with_metadata(self, gcs, mock_storage_client):
        """Should set metadata on JSON blob."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        metadata = {"source": "test"}
        gcs.upload_json({"key": "val"}, "data/out.json", metadata=metadata)

        assert mock_blob.metadata == metadata


class TestDownloadFile:
    """Tests for download_file method."""

    def test_download_file(self, gcs, mock_storage_client, tmp_path):
        """Should download blob to local path."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        local_path = tmp_path / "subdir" / "downloaded.mp3"
        result = gcs.download_file("audio/test.mp3", local_path)

        mock_bucket.blob.assert_called_once_with("audio/test.mp3")
        mock_blob.download_to_filename.assert_called_once_with(str(local_path))
        assert result == local_path
        # Parent directory should be created
        assert local_path.parent.exists()

    def test_download_file_creates_parent_dirs(self, gcs, mock_storage_client, tmp_path):
        """Should create parent directories if they don't exist."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        nested_path = tmp_path / "a" / "b" / "c" / "file.txt"
        gcs.download_file("some/blob.txt", nested_path)

        assert nested_path.parent.exists()


class TestDownloadJson:
    """Tests for download_json method."""

    def test_download_json(self, gcs, mock_storage_client):
        """Should download and parse JSON."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        expected = {"key": "value", "nested": {"a": 1}}
        mock_blob.download_as_text.return_value = json.dumps(expected)

        result = gcs.download_json("data/output.json")

        mock_bucket.blob.assert_called_once_with("data/output.json")
        assert result == expected

    def test_download_json_list(self, gcs, mock_storage_client):
        """Should handle JSON list responses."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        expected = [1, 2, 3]
        mock_blob.download_as_text.return_value = json.dumps(expected)

        result = gcs.download_json("data/list.json")
        assert result == expected


class TestExists:
    """Tests for exists method."""

    def test_exists_true(self, gcs, mock_storage_client):
        """Should return True when blob exists."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True

        assert gcs.exists("path/to/file.txt") is True

    def test_exists_false(self, gcs, mock_storage_client):
        """Should return False when blob does not exist."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = False

        assert gcs.exists("path/to/missing.txt") is False


class TestDelete:
    """Tests for delete method."""

    def test_delete_existing_blob(self, gcs, mock_storage_client):
        """Should delete blob and return True."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        result = gcs.delete("path/to/file.txt")

        mock_blob.delete.assert_called_once()
        assert result is True

    def test_delete_nonexistent_blob(self, gcs, mock_storage_client):
        """Should return False when blob doesn't exist."""
        from ponderosa.storage import gcs_client as _mod

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.delete.side_effect = _mod.NotFound("not found")

        result = gcs.delete("path/to/missing.txt")

        assert result is False


class TestListBlobs:
    """Tests for list_blobs method."""

    def test_list_blobs_no_filter(self, gcs, mock_storage_client):
        """Should list all blobs in bucket."""
        mock_blob1 = MagicMock()
        mock_blob1.name = "file1.txt"
        mock_blob2 = MagicMock()
        mock_blob2.name = "file2.txt"
        mock_storage_client.list_blobs.return_value = [mock_blob1, mock_blob2]

        result = gcs.list_blobs()

        mock_storage_client.list_blobs.assert_called_once_with(
            BUCKET_NAME, prefix=None, delimiter=None, max_results=None
        )
        assert result == ["file1.txt", "file2.txt"]

    def test_list_blobs_with_prefix(self, gcs, mock_storage_client):
        """Should pass prefix to list_blobs."""
        mock_storage_client.list_blobs.return_value = []

        gcs.list_blobs(prefix="audio/")

        mock_storage_client.list_blobs.assert_called_once_with(
            BUCKET_NAME, prefix="audio/", delimiter=None, max_results=None
        )

    def test_list_blobs_with_all_params(self, gcs, mock_storage_client):
        """Should pass all parameters to list_blobs."""
        mock_storage_client.list_blobs.return_value = []

        gcs.list_blobs(prefix="audio/", delimiter="/", max_results=10)

        mock_storage_client.list_blobs.assert_called_once_with(
            BUCKET_NAME, prefix="audio/", delimiter="/", max_results=10
        )

    def test_list_blobs_empty(self, gcs, mock_storage_client):
        """Should return empty list when no blobs found."""
        mock_storage_client.list_blobs.return_value = []

        result = gcs.list_blobs()
        assert result == []


class TestCreateBucketIfNotExists:
    """Tests for create_bucket_if_not_exists method."""

    def test_bucket_already_exists(self, gcs, mock_storage_client):
        """Should not create bucket if it already exists."""
        mock_storage_client.get_bucket.return_value = MagicMock()

        gcs.create_bucket_if_not_exists()

        mock_storage_client.get_bucket.assert_called_once_with(BUCKET_NAME)
        mock_storage_client.create_bucket.assert_not_called()

    def test_bucket_does_not_exist(self, gcs, mock_storage_client):
        """Should create bucket when it doesn't exist."""
        from ponderosa.storage import gcs_client as _mod

        mock_storage_client.get_bucket.side_effect = _mod.NotFound("not found")
        mock_storage_client.create_bucket.return_value = MagicMock(name=BUCKET_NAME)

        gcs.create_bucket_if_not_exists()

        mock_storage_client.get_bucket.assert_called_once_with(BUCKET_NAME)
        mock_storage_client.create_bucket.assert_called_once_with(
            BUCKET_NAME, location="us-central1"
        )

    def test_bucket_create_custom_location(self, gcs, mock_storage_client):
        """Should use custom location when specified."""
        from ponderosa.storage import gcs_client as _mod

        mock_storage_client.get_bucket.side_effect = _mod.NotFound("not found")
        mock_storage_client.create_bucket.return_value = MagicMock(name=BUCKET_NAME)

        gcs.create_bucket_if_not_exists(location="europe-west1")

        mock_storage_client.create_bucket.assert_called_once_with(
            BUCKET_NAME, location="europe-west1"
        )
