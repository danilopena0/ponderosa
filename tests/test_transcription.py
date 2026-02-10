"""Tests for the Transcriber."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ponderosa.transcription import Segment, TranscriptionResult, Transcriber


class TestTranscriptionResult:
    """Tests for the TranscriptionResult model."""

    def test_basic_result(self):
        result = TranscriptionResult(
            text="Hello world",
            segments=[Segment(start=0.0, end=2.0, text="Hello world")],
            language="en",
            duration=2.0,
        )
        assert result.text == "Hello world"
        assert len(result.segments) == 1
        assert result.language == "en"
        assert result.duration == 2.0

    def test_empty_segments(self):
        result = TranscriptionResult(
            text="",
            segments=[],
            language="en",
            duration=0.0,
        )
        assert result.segments == []

    def test_serialization(self):
        result = TranscriptionResult(
            text="Test",
            segments=[Segment(start=0.0, end=1.0, text="Test")],
            language="en",
            duration=1.0,
        )
        data = result.model_dump()
        assert data["text"] == "Test"
        assert data["segments"][0]["start"] == 0.0


class TestSegment:
    """Tests for the Segment model."""

    def test_basic_segment(self):
        seg = Segment(start=1.5, end=3.2, text="Hello")
        assert seg.start == 1.5
        assert seg.end == 3.2
        assert seg.text == "Hello"


class TestTranscriberInit:
    """Tests for Transcriber initialization."""

    def test_defaults(self):
        t = Transcriber()
        assert t.model_size == "base"
        assert t.device == "cpu"
        assert t.compute_type == "int8"
        assert t.language == "en"
        assert t._model is None

    def test_custom_params(self):
        t = Transcriber(
            model_size="large-v3",
            device="cuda",
            compute_type="float16",
            language="fr",
        )
        assert t.model_size == "large-v3"
        assert t.device == "cuda"
        assert t.compute_type == "float16"
        assert t.language == "fr"


class TestTranscriberModel:
    """Tests for lazy model loading."""

    @patch("faster_whisper.WhisperModel")
    def test_lazy_load(self, mock_whisper_cls):
        t = Transcriber(model_size="tiny")
        assert t._model is None

        _ = t.model

        mock_whisper_cls.assert_called_once_with("tiny", device="cpu", compute_type="int8")
        assert t._model is not None

    @patch("faster_whisper.WhisperModel")
    def test_model_reused(self, mock_whisper_cls):
        t = Transcriber()
        m1 = t.model
        m2 = t.model
        assert m1 is m2
        mock_whisper_cls.assert_called_once()


class TestTranscribe:
    """Tests for the transcribe method."""

    @patch("faster_whisper.WhisperModel")
    def test_basic_transcription(self, mock_whisper_cls, tmp_path):
        mock_seg1 = MagicMock()
        mock_seg1.start = 0.0
        mock_seg1.end = 2.5
        mock_seg1.text = " Hello world"

        mock_seg2 = MagicMock()
        mock_seg2.start = 2.5
        mock_seg2.end = 5.0
        mock_seg2.text = " How are you"

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.duration = 5.0

        mock_whisper_cls.return_value.transcribe.return_value = (
            iter([mock_seg1, mock_seg2]),
            mock_info,
        )

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        t = Transcriber()
        result = t.transcribe(audio_file)

        assert isinstance(result, TranscriptionResult)
        assert result.text == "Hello world How are you"
        assert len(result.segments) == 2
        assert result.segments[0].text == "Hello world"
        assert result.segments[1].text == "How are you"
        assert result.language == "en"
        assert result.duration == 5.0

    @patch("faster_whisper.WhisperModel")
    def test_empty_transcription(self, mock_whisper_cls, tmp_path):
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.duration = 0.0

        mock_whisper_cls.return_value.transcribe.return_value = (iter([]), mock_info)

        audio_file = tmp_path / "silence.mp3"
        audio_file.write_bytes(b"fake")

        t = Transcriber()
        result = t.transcribe(audio_file)

        assert result.text == ""
        assert result.segments == []

    @patch("faster_whisper.WhisperModel")
    def test_passes_language(self, mock_whisper_cls, tmp_path):
        mock_info = MagicMock()
        mock_info.language = "fr"
        mock_info.duration = 1.0

        mock_whisper_cls.return_value.transcribe.return_value = (iter([]), mock_info)

        audio_file = tmp_path / "french.mp3"
        audio_file.write_bytes(b"fake")

        t = Transcriber(language="fr")
        t.transcribe(audio_file)

        mock_whisper_cls.return_value.transcribe.assert_called_once_with(
            str(audio_file),
            language="fr",
        )
