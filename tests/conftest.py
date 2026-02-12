"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def sample_episode_data() -> dict:
    """Sample episode data for testing."""
    return {
        "id": "abc123def456",
        "guid": "https://example.com/episode/123",
        "title": "Test Episode: Understanding Markets",
        "description": "A discussion about market dynamics.",
        "audio_url": "https://example.com/audio/episode123.mp3",
        "audio_format": "mp3",
        "duration_seconds": 3600,
    }
