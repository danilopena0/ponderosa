"""Tests for the FastAPI search API."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ponderosa.api import app, get_store


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.list_episodes.return_value = [
        {"id": "ep-001", "episode_title": "Test Episode"},
    ]
    store.get_episode.return_value = {
        "id": "ep-001",
        "summary": "A test summary.",
        "episode_title": "Test Episode",
        "themes": [],
        "learnings": [],
        "strategies": [],
    }
    store.search_themes.return_value = [
        {"id": "ep-001_themes_0", "document": "Trend Following: A strategy.", "name": "Trend Following", "distance": 0.1},
    ]
    store.search_learnings.return_value = [
        {"id": "ep-001_learnings_0", "document": "Risk: Important.", "name": "Risk Management", "distance": 0.2},
    ]
    store.search_strategies.return_value = [
        {"id": "ep-001_strategies_0", "document": "Rebalance: Monthly.", "name": "Rebalancing", "distance": 0.15},
    ]
    store.search_all.return_value = {
        "themes": store.search_themes.return_value,
        "learnings": store.search_learnings.return_value,
        "strategies": store.search_strategies.return_value,
    }
    return store


@pytest.fixture
def client(mock_store):
    import ponderosa.api as api_module

    api_module._store = mock_store
    yield TestClient(app)
    api_module._store = None


class TestAPI:
    def test_list_episodes(self, client, mock_store):
        response = client.get("/episodes")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "ep-001"

    def test_get_episode(self, client, mock_store):
        response = client.get("/episodes/ep-001")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "ep-001"
        assert data["summary"] == "A test summary."

    def test_get_episode_not_found(self, client, mock_store):
        mock_store.get_episode.return_value = None
        response = client.get("/episodes/nonexistent")
        assert response.status_code == 200
        assert response.json()["error"] == "Episode not found"

    def test_search_themes(self, client, mock_store):
        response = client.get("/search/themes?q=trend+following")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Trend Following"

    def test_search_learnings(self, client, mock_store):
        response = client.get("/search/learnings?q=risk")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_search_strategies(self, client, mock_store):
        response = client.get("/search/strategies?q=rebalance")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_search_all(self, client, mock_store):
        response = client.get("/search?q=market")
        assert response.status_code == 200
        data = response.json()
        assert "themes" in data
        assert "learnings" in data
        assert "strategies" in data

    def test_search_requires_query(self, client):
        response = client.get("/search/themes")
        assert response.status_code == 422  # validation error
