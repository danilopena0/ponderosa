"""FastAPI search API for querying enriched podcast data."""

from fastapi import FastAPI, Query

from ponderosa.storage import PonderosaStore

app = FastAPI(
    title="Ponderosa",
    description="Podcast Intelligence Pipeline - Search API",
    version="0.1.0",
)

_store: PonderosaStore | None = None


def get_store() -> PonderosaStore:
    global _store
    if _store is None:
        _store = PonderosaStore()
    return _store


@app.get("/episodes")
def list_episodes():
    """List all enriched episodes."""
    return get_store().list_episodes()


@app.get("/episodes/{episode_id}")
def get_episode(episode_id: str):
    """Get full enrichment for an episode."""
    result = get_store().get_episode(episode_id)
    if result is None:
        return {"error": "Episode not found"}
    return result


@app.get("/search/themes")
def search_themes(q: str = Query(..., description="Search query"), limit: int = 10):
    """Search across themes."""
    return get_store().search_themes(q, limit)


@app.get("/search/learnings")
def search_learnings(q: str = Query(..., description="Search query"), limit: int = 10):
    """Search across learnings."""
    return get_store().search_learnings(q, limit)


@app.get("/search/strategies")
def search_strategies(q: str = Query(..., description="Search query"), limit: int = 10):
    """Search across strategies."""
    return get_store().search_strategies(q, limit)


@app.get("/search")
def search_all(q: str = Query(..., description="Search query"), limit: int = 10):
    """Search across all collections."""
    return get_store().search_all(q, limit)
