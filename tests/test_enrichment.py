"""Tests for the enrichment module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ponderosa.enrichment import Enricher, EnrichmentResult, Insight, _chunk_text


MOCK_PERPLEXITY_RESPONSE = json.dumps({
    "episode_title": "Test Episode: Market Trends",
    "summary": "A discussion about market trends and strategies.",
    "themes": [
        {
            "name": "Trend Following",
            "description": "Systematic approach to capturing market trends.",
            "keywords": ["trend", "momentum", "systematic"],
            "relevance_score": 0.9,
        },
    ],
    "learnings": [
        {
            "name": "Diversification Matters",
            "description": "Spreading risk across uncorrelated strategies improves returns.",
            "keywords": ["diversification", "risk", "correlation"],
            "relevance_score": 0.85,
        },
    ],
    "strategies": [
        {
            "name": "Momentum Rebalancing",
            "description": "Rebalance portfolios based on momentum signals monthly.",
            "keywords": ["momentum", "rebalancing", "portfolio"],
            "relevance_score": 0.8,
        },
    ],
})


class TestEnrichmentResult:
    def test_create_from_dict(self):
        data = json.loads(MOCK_PERPLEXITY_RESPONSE)
        result = EnrichmentResult(**data)
        assert result.episode_title == "Test Episode: Market Trends"
        assert len(result.themes) == 1
        assert len(result.learnings) == 1
        assert len(result.strategies) == 1

    def test_empty_defaults(self):
        result = EnrichmentResult()
        assert result.themes == []
        assert result.learnings == []
        assert result.strategies == []
        assert result.summary == ""

    def test_insight_model(self):
        insight = Insight(
            name="Test",
            description="A test insight",
            keywords=["test"],
            relevance_score=0.75,
        )
        assert insight.name == "Test"
        assert insight.relevance_score == 0.75


class TestChunking:
    def test_short_text_single_chunk(self):
        chunks = _chunk_text("Short text.", chunk_size=100, overlap=10)
        assert len(chunks) == 1
        assert chunks[0] == "Short text."

    def test_long_text_splits(self):
        # Create text that's 250 chars with sentences
        text = "Hello world. " * 20  # ~260 chars
        chunks = _chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) >= 2
        # All original text should be covered
        for word in ["Hello", "world"]:
            assert any(word in c for c in chunks)

    def test_breaks_at_sentence_boundary(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."
        chunks = _chunk_text(text, chunk_size=50, overlap=10)
        # Chunks should end at sentence boundaries, not mid-word
        for chunk in chunks[:-1]:  # last chunk can end anywhere
            assert chunk.rstrip().endswith(".") or chunk.rstrip().endswith("?") or chunk.rstrip().endswith("!")


class TestEnricher:
    def _setup_enricher_mocks(
        self,
        mock_settings: MagicMock,
        mock_openai_cls: MagicMock,
        response_content: str = MOCK_PERPLEXITY_RESPONSE,
    ) -> tuple[MagicMock, Enricher]:
        """Configure common mocks for Enricher tests and return (mock_client, enricher)."""
        mock_settings.return_value.perplexity.api_key = "test-key"
        mock_settings.return_value.perplexity.base_url = "https://api.perplexity.ai"
        mock_settings.return_value.perplexity.model = "sonar-pro"

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = response_content
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        return mock_client, Enricher()

    @patch("ponderosa.enrichment.get_settings")
    @patch("ponderosa.enrichment.OpenAI")
    def test_enrich_transcript(self, mock_openai_cls, mock_settings, tmp_path):
        mock_client, enricher = self._setup_enricher_mocks(mock_settings, mock_openai_cls)

        # Create test transcript
        transcript = {"text": "This is a test transcript about market trends."}
        transcript_path = tmp_path / "test.transcript.json"
        transcript_path.write_text(json.dumps(transcript))

        result = enricher.enrich_transcript(transcript_path)

        assert isinstance(result, EnrichmentResult)
        assert result.episode_title == "Test Episode: Market Trends"
        assert len(result.themes) == 1
        assert result.themes[0].name == "Trend Following"
        mock_client.chat.completions.create.assert_called_once()

    @patch("ponderosa.enrichment.get_settings")
    @patch("ponderosa.enrichment.OpenAI")
    def test_enrich_strips_markdown_fences(self, mock_openai_cls, mock_settings, tmp_path):
        fenced = f"```json\n{MOCK_PERPLEXITY_RESPONSE}\n```"
        mock_client, enricher = self._setup_enricher_mocks(
            mock_settings, mock_openai_cls, response_content=fenced,
        )

        transcript = {"text": "Test transcript."}
        transcript_path = tmp_path / "test.transcript.json"
        transcript_path.write_text(json.dumps(transcript))

        result = enricher.enrich_transcript(transcript_path)

        assert result.episode_title == "Test Episode: Market Trends"

    @patch("ponderosa.enrichment.get_settings")
    @patch("ponderosa.enrichment.OpenAI")
    def test_enrich_uses_segments_fallback(self, mock_openai_cls, mock_settings, tmp_path):
        mock_client, enricher = self._setup_enricher_mocks(mock_settings, mock_openai_cls)

        # Transcript with segments but no top-level text
        transcript = {
            "text": "",
            "segments": [
                {"text": "Hello world.", "start": 0, "end": 1},
                {"text": "Goodbye.", "start": 1, "end": 2},
            ],
        }
        transcript_path = tmp_path / "test.transcript.json"
        transcript_path.write_text(json.dumps(transcript))

        result = enricher.enrich_transcript(transcript_path)

        # Verify the call was made (segments were concatenated)
        call_args = mock_client.chat.completions.create.call_args
        user_content = call_args[1]["messages"][1]["content"]
        assert "Hello world." in user_content
        assert "Goodbye." in user_content

    @patch("ponderosa.enrichment._chunk_text")
    @patch("ponderosa.enrichment.get_settings")
    @patch("ponderosa.enrichment.OpenAI")
    def test_enrich_chunks_long_transcript(self, mock_openai_cls, mock_settings, mock_chunk, tmp_path):
        mock_client, enricher = self._setup_enricher_mocks(mock_settings, mock_openai_cls)

        # Force chunking into 2 pieces
        mock_chunk.return_value = ["Chunk one text.", "Chunk two text."]

        transcript = {"text": "Some transcript text."}
        transcript_path = tmp_path / "test.transcript.json"
        transcript_path.write_text(json.dumps(transcript))

        result = enricher.enrich_transcript(transcript_path)

        assert isinstance(result, EnrichmentResult)
        # 2 chunk calls + 1 merge call = 3
        assert mock_client.chat.completions.create.call_count == 3
