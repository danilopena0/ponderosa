"""Tests for the ChromaDB storage module."""

from unittest.mock import patch

import pytest

from ponderosa.enrichment import EnrichmentResult, Insight
from ponderosa.storage import PonderosaStore


@pytest.fixture
def store(tmp_path):
    """Create a PonderosaStore with a temporary directory."""
    with patch("ponderosa.storage.get_settings") as mock_settings:
        mock_settings.return_value.chroma.persist_directory = str(tmp_path / "chroma")
        yield PonderosaStore(persist_directory=str(tmp_path / "chroma"))


@pytest.fixture
def sample_enrichment():
    return EnrichmentResult(
        episode_title="Test Episode",
        summary="A summary of the test episode about markets.",
        themes=[
            Insight(
                name="Trend Following",
                description="Systematic trend capture strategies.",
                keywords=["trend", "momentum"],
                relevance_score=0.9,
            ),
        ],
        learnings=[
            Insight(
                name="Risk Management",
                description="Position sizing is critical for long-term survival.",
                keywords=["risk", "sizing"],
                relevance_score=0.85,
            ),
        ],
        strategies=[
            Insight(
                name="Monthly Rebalancing",
                description="Rebalance portfolio monthly based on signals.",
                keywords=["rebalance", "monthly"],
                relevance_score=0.8,
            ),
        ],
    )


class TestPonderosaStore:
    def test_store_and_list_episodes(self, store, sample_enrichment):
        store.store_enrichment("ep-001", sample_enrichment)
        episodes = store.list_episodes()
        assert len(episodes) == 1
        assert episodes[0]["id"] == "ep-001"
        assert episodes[0]["episode_title"] == "Test Episode"

    def test_get_episode(self, store, sample_enrichment):
        store.store_enrichment("ep-001", sample_enrichment)
        episode = store.get_episode("ep-001")
        assert episode is not None
        assert episode["id"] == "ep-001"
        assert episode["summary"] == sample_enrichment.summary
        assert len(episode["themes"]) == 1
        assert len(episode["learnings"]) == 1
        assert len(episode["strategies"]) == 1

    def test_get_missing_episode(self, store):
        result = store.get_episode("nonexistent")
        assert result is None

    def test_search_themes(self, store, sample_enrichment):
        store.store_enrichment("ep-001", sample_enrichment)
        results = store.search_themes("trend following momentum", limit=5)
        assert len(results) >= 1
        assert results[0]["name"] == "Trend Following"

    def test_search_learnings(self, store, sample_enrichment):
        store.store_enrichment("ep-001", sample_enrichment)
        results = store.search_learnings("risk management", limit=5)
        assert len(results) >= 1
        assert results[0]["name"] == "Risk Management"

    def test_search_strategies(self, store, sample_enrichment):
        store.store_enrichment("ep-001", sample_enrichment)
        results = store.search_strategies("rebalancing portfolio", limit=5)
        assert len(results) >= 1
        assert results[0]["name"] == "Monthly Rebalancing"

    def test_search_all(self, store, sample_enrichment):
        store.store_enrichment("ep-001", sample_enrichment)
        results = store.search_all("market trends", limit=5)
        assert "themes" in results
        assert "learnings" in results
        assert "strategies" in results

    def test_upsert_overwrites(self, store, sample_enrichment):
        store.store_enrichment("ep-001", sample_enrichment)
        # Modify and re-store
        sample_enrichment.episode_title = "Updated Episode"
        store.store_enrichment("ep-001", sample_enrichment)
        episodes = store.list_episodes()
        assert len(episodes) == 1
        assert episodes[0]["episode_title"] == "Updated Episode"
