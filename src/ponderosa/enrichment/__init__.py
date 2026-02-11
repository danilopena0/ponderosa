"""Enrichment module for transcript analysis using Perplexity API.

Extracts structured insights (themes, learnings, strategies) from podcast transcripts.
"""

import json
from pathlib import Path

import structlog
from openai import OpenAI
from pydantic import BaseModel, Field

from ponderosa.config import get_settings

logger = structlog.get_logger(__name__)

ENRICHMENT_PROMPT = """Analyze this podcast transcript and extract structured insights.

Return a JSON object with exactly this structure:
{
  "episode_title": "string - the episode title if mentioned, or a descriptive title",
  "summary": "string - 2-3 paragraph summary of the episode",
  "themes": [
    {
      "name": "string - theme name",
      "description": "string - 1-2 sentence description",
      "keywords": ["keyword1", "keyword2"],
      "relevance_score": 0.0-1.0
    }
  ],
  "learnings": [
    {
      "name": "string - learning name",
      "description": "string - 1-2 sentence description of the insight",
      "keywords": ["keyword1", "keyword2"],
      "relevance_score": 0.0-1.0
    }
  ],
  "strategies": [
    {
      "name": "string - strategy name",
      "description": "string - 1-2 sentence description of the actionable strategy",
      "keywords": ["keyword1", "keyword2"],
      "relevance_score": 0.0-1.0
    }
  ]
}

Extract 3-7 items for each category. Be specific and actionable.
Only return valid JSON, no markdown formatting.

TRANSCRIPT:
"""

MERGE_PROMPT = """You are given multiple JSON enrichment results extracted from different chunks of the same podcast episode. Merge them into a single coherent result.

Rules:
- Deduplicate: if two themes/learnings/strategies are about the same concept, merge them into one with the better description and combined keywords
- Keep the best episode_title (most descriptive)
- Combine the summaries into one coherent 2-3 paragraph summary
- Keep 3-7 items per category, selecting the highest relevance_score items
- Return valid JSON only, no markdown formatting

Return the same JSON structure:
{
  "episode_title": "string",
  "summary": "string",
  "themes": [...],
  "learnings": [...],
  "strategies": [...]
}

CHUNK RESULTS:
"""

CHUNK_SIZE = 60000
CHUNK_OVERLAP = 2000
MAX_RETRIES = 2


class Insight(BaseModel):
    """A single extracted insight (theme, learning, or strategy)."""

    name: str
    description: str
    keywords: list[str] = Field(default_factory=list)
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)


class EnrichmentResult(BaseModel):
    """Structured enrichment output from a transcript."""

    episode_title: str = ""
    summary: str = ""
    themes: list[Insight] = Field(default_factory=list)
    learnings: list[Insight] = Field(default_factory=list)
    strategies: list[Insight] = Field(default_factory=list)


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks at sentence boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            # Try to break at a sentence boundary (. ! ?)
            boundary = text.rfind(". ", start + chunk_size - 5000, end)
            if boundary == -1:
                boundary = text.rfind("? ", start + chunk_size - 5000, end)
            if boundary == -1:
                boundary = text.rfind("! ", start + chunk_size - 5000, end)
            if boundary != -1:
                end = boundary + 1  # include the period

        chunks.append(text[start:end])
        start = end - overlap

    return chunks


class Enricher:
    """Extracts structured insights from transcripts using Perplexity API."""

    def __init__(self) -> None:
        settings = get_settings()
        self.client = OpenAI(
            api_key=settings.perplexity.api_key,
            base_url=settings.perplexity.base_url,
        )
        self.model = settings.perplexity.model
        self.logger = logger.bind(component="enricher")

    def enrich_transcript(self, transcript_path: Path) -> EnrichmentResult:
        """Enrich a transcript JSON file.

        Args:
            transcript_path: Path to a transcript JSON file (from Transcriber).

        Returns:
            EnrichmentResult with extracted themes, learnings, and strategies.
        """
        self.logger.info("Enriching transcript", path=str(transcript_path))

        data = json.loads(transcript_path.read_text())
        text = data.get("text", "")
        if not text:
            segments = data.get("segments", [])
            text = " ".join(s.get("text", "") for s in segments)

        print(f"  Transcript length: {len(text):,} chars")

        chunks = _chunk_text(text)

        if len(chunks) == 1:
            print(f"  Sending to Perplexity ({self.model})... this may take 30-60s")
            self.logger.info("Sending single chunk to Perplexity", model=self.model, chars=len(text))
            return self._enrich_single(chunks[0])

        print(f"  Transcript split into {len(chunks)} chunks (overlap: {CHUNK_OVERLAP:,} chars)")
        self.logger.info("Chunking transcript", chunks=len(chunks), chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        chunk_results = []
        for i, chunk in enumerate(chunks, 1):
            print(f"  Processing chunk {i}/{len(chunks)} ({len(chunk):,} chars)...")
            self.logger.info("Processing chunk", chunk=i, total=len(chunks), chars=len(chunk))
            result = self._enrich_single(chunk)
            chunk_results.append(result)

        print("  Merging chunk results...")
        self.logger.info("Merging chunk results", chunks=len(chunk_results))
        merged = self._merge_results(chunk_results)

        self.logger.info(
            "Enrichment complete",
            chunks=len(chunks),
            themes=len(merged.themes),
            learnings=len(merged.learnings),
            strategies=len(merged.strategies),
        )

        return merged

    def _call_llm(self, system: str, prompt: str) -> EnrichmentResult:
        """Call the LLM and parse the response, retrying on validation errors."""
        last_error = None
        for attempt in range(1, MAX_RETRIES + 2):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )

            raw = response.choices[0].message.content.strip()
            raw = _strip_code_fences(raw)

            try:
                parsed = json.loads(raw)
                return EnrichmentResult(**parsed)
            except (json.JSONDecodeError, Exception) as e:
                last_error = e
                if attempt <= MAX_RETRIES:
                    print(f"  Validation failed (attempt {attempt}/{MAX_RETRIES + 1}): {e}")
                    print(f"  Retrying...")
                    self.logger.warning(
                        "LLM response validation failed, retrying",
                        attempt=attempt,
                        error=str(e),
                    )

        raise RuntimeError(
            f"Failed to get valid response after {MAX_RETRIES + 1} attempts. "
            f"Last error: {last_error}\n"
            f"Please run the command again."
        )

    def _enrich_single(self, text: str) -> EnrichmentResult:
        """Enrich a single chunk of text."""
        return self._call_llm(
            system="You are an expert podcast analyst. Return only valid JSON.",
            prompt=ENRICHMENT_PROMPT + text,
        )

    def _merge_results(self, results: list[EnrichmentResult]) -> EnrichmentResult:
        """Merge multiple chunk results using the LLM to deduplicate."""
        results_json = json.dumps(
            [r.model_dump() for r in results], indent=2
        )
        return self._call_llm(
            system="You are an expert at synthesizing information. Return only valid JSON.",
            prompt=MERGE_PROMPT + results_json,
        )


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM response."""
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    return text
