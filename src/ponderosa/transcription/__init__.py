"""Transcription module using faster-whisper for local speech-to-text."""

from pathlib import Path

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class Segment(BaseModel):
    """A single transcription segment."""

    start: float
    end: float
    text: str


class TranscriptionResult(BaseModel):
    """Result of transcribing an audio file."""

    text: str
    segments: list[Segment]
    language: str
    duration: float


class Transcriber:
    """Transcribes audio files using faster-whisper."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en",
    ) -> None:
        """Initialize the transcriber.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v3).
            device: Device to run on (cpu, cuda).
            compute_type: Compute type (int8, float16, float32).
            language: Language code for transcription.
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model = None
        self.logger = logger.bind(component="transcriber")

    @property
    def model(self):
        """Lazy-load the whisper model."""
        if self._model is None:
            from faster_whisper import WhisperModel

            self.logger.info(
                "Loading whisper model",
                model_size=self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe an audio file.

        Args:
            audio_path: Path to the audio file.

        Returns:
            TranscriptionResult with full text, segments, language, and duration.
        """
        self.logger.info("Transcribing audio", path=str(audio_path))

        segments_iter, info = self.model.transcribe(
            str(audio_path),
            language=self.language,
        )

        segments = []
        text_parts = []
        for segment in segments_iter:
            segments.append(Segment(
                start=segment.start,
                end=segment.end,
                text=segment.text.strip(),
            ))
            text_parts.append(segment.text.strip())

        full_text = " ".join(text_parts)

        self.logger.info(
            "Transcription complete",
            language=info.language,
            duration=info.duration,
            segments=len(segments),
        )

        return TranscriptionResult(
            text=full_text,
            segments=segments,
            language=info.language,
            duration=info.duration,
        )
