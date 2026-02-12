"""Storage module using ChromaDB for vector search over enriched podcast data."""

import hashlib
from pathlib import Path

import chromadb
import structlog

from ponderosa.config import get_settings
from ponderosa.enrichment import EnrichmentResult

logger = structlog.get_logger(__name__)

COLLECTIONS = ("themes", "learnings", "strategies")
SHORT_ID_LENGTH = 8


def make_short_id(episode_id: str) -> str:
    """Generate a short 8-char hash from a full episode ID."""
    return hashlib.sha256(episode_id.encode()).hexdigest()[:SHORT_ID_LENGTH]


class PonderosaStore:
    """ChromaDB wrapper for storing and searching enriched podcast data."""

    def __init__(self, persist_directory: str | None = None) -> None:
        settings = get_settings()
        persist_dir = persist_directory or settings.chroma.persist_directory
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=persist_dir)
        self.episodes = self.client.get_or_create_collection("episodes")
        self.themes = self.client.get_or_create_collection("themes")
        self.learnings = self.client.get_or_create_collection("learnings")
        self.strategies = self.client.get_or_create_collection("strategies")
        self.logger = logger.bind(component="store")

    def store_enrichment(self, episode_id: str, result: EnrichmentResult) -> None:
        """Store an enrichment result in all collections.

        Args:
            episode_id: Unique episode identifier.
            result: Enrichment result to store.
        """
        # Check if this episode already exists
        existing = self.episodes.get(ids=[episode_id])
        if existing["ids"]:
            self.logger.info("Episode already exists, upserting", episode_id=episode_id)
            self.logger.info("Upserting existing episode", episode_id=episode_id)
        else:
            self.logger.info("Storing new episode", episode_id=episode_id)
            self.logger.info("Storing new episode", episode_id=episode_id)

        short_id = make_short_id(episode_id)

        # Store episode-level data
        self.episodes.upsert(
            ids=[episode_id],
            documents=[result.summary],
            metadatas=[{
                "episode_title": result.episode_title,
                "short_id": short_id,
                "themes_count": len(result.themes),
                "learnings_count": len(result.learnings),
                "strategies_count": len(result.strategies),
            }],
        )

        # Store insights in their respective collections
        for collection_name in COLLECTIONS:
            collection = getattr(self, collection_name)
            insights = getattr(result, collection_name)
            if not insights:
                continue

            ids = [f"{episode_id}_{collection_name}_{i}" for i in range(len(insights))]
            documents = [f"{ins.name}: {ins.description}" for ins in insights]
            metadatas = [
                {
                    "episode_id": episode_id,
                    "episode_title": result.episode_title,
                    "name": ins.name,
                    "keywords": ", ".join(ins.keywords),
                    "relevance_score": ins.relevance_score,
                }
                for ins in insights
            ]

            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

        self.logger.info("Enrichment stored", episode_id=episode_id)

    def search_themes(self, query: str, limit: int = 10) -> list[dict]:
        """Semantic search across themes."""
        return self._search(self.themes, query, limit)

    def search_learnings(self, query: str, limit: int = 10) -> list[dict]:
        """Semantic search across learnings."""
        return self._search(self.learnings, query, limit)

    def search_strategies(self, query: str, limit: int = 10) -> list[dict]:
        """Semantic search across strategies."""
        return self._search(self.strategies, query, limit)

    def search_all(self, query: str, limit: int = 10) -> dict[str, list[dict]]:
        """Search across all collections."""
        return {
            "themes": self.search_themes(query, limit),
            "learnings": self.search_learnings(query, limit),
            "strategies": self.search_strategies(query, limit),
        }

    def resolve_episode_id(self, id_or_short: str) -> str | None:
        """Resolve a short ID or full ID to the full episode ID.

        Args:
            id_or_short: Either a full episode ID or a short 8-char hash.

        Returns:
            The full episode ID, or None if not found.
        """
        # Try as full ID first
        result = self.episodes.get(ids=[id_or_short])
        if result["ids"]:
            return id_or_short

        # Try as short ID
        all_eps = self.episodes.get(include=["metadatas"])
        for eid, meta in zip(all_eps["ids"], all_eps["metadatas"]):
            if meta.get("short_id") == id_or_short:
                return eid

        return None

    def get_episode(self, episode_id: str) -> dict | None:
        """Get all data for an episode. Accepts full ID or short ID."""
        # Resolve short IDs
        resolved = self.resolve_episode_id(episode_id)
        if not resolved:
            return None
        episode_id = resolved

        result = self.episodes.get(ids=[episode_id], include=["documents", "metadatas"])
        if not result["ids"]:
            return None

        episode = {
            "id": episode_id,
            "summary": result["documents"][0],
            **result["metadatas"][0],
        }

        # Gather insights from sub-collections
        for name in COLLECTIONS:
            collection = getattr(self, name)
            items = collection.get(
                where={"episode_id": episode_id},
                include=["documents", "metadatas"],
            )
            episode[name] = [
                {"document": doc, **meta}
                for doc, meta in zip(items["documents"], items["metadatas"])
            ]

        return episode

    def list_episodes(self) -> list[dict]:
        """List all indexed episodes."""
        result = self.episodes.get(include=["metadatas"])
        return [
            {"id": eid, **meta}
            for eid, meta in zip(result["ids"], result["metadatas"])
        ]

    @staticmethod
    def _search(collection, query: str, limit: int) -> list[dict]:
        """Run a semantic search on a collection."""
        results = collection.query(query_texts=[query], n_results=limit)
        items = []
        for i in range(len(results["ids"][0])):
            items.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "distance": results["distances"][0][i],
                **results["metadatas"][0][i],
            })
        return items
