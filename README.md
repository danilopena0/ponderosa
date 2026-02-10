# Ponderosa - Podcast Intelligence Pipeline

A local-first pipeline for podcast transcription, enrichment, and semantic search.

## Overview

Ponderosa processes podcasts through a complete pipeline — all running locally with no cloud dependencies:

1. **Ingestion** - Parse RSS feeds and download audio locally
2. **Transcription** - Convert audio to text using faster-whisper (local Whisper)
3. **Enrichment** - Summarize and extract topics (coming soon)
4. **Search** - Semantic search (coming soon)
5. **API** - FastAPI interface (coming soon)

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager

### Installation

#### Linux / macOS

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/yourusername/ponderosa.git
cd ponderosa

# Create virtual environment and install dependencies
uv venv --python 3.13
source .venv/bin/activate
uv sync --all-extras

# Copy environment template
cp .env.example .env
```

#### Windows (PowerShell)

```powershell
# Install uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Add uv to PATH permanently (restart terminal after this)
[Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";$env:USERPROFILE\.local\bin", "User")

# Clone the repository
git clone https://github.com/yourusername/ponderosa.git
cd ponderosa

# Create virtual environment and install dependencies
uv venv --python 3.13
.venv\Scripts\activate
uv sync --all-extras

# Copy environment template
copy .env.example .env
```

> **Note:** If PowerShell blocks the activate script, run:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### Try It Out

```bash
# Parse a podcast feed
uv run ponderosa parse-feed "https://flirtingwithmodels.libsyn.com/rss" -n 5

# Download 1 episode locally
uv run ponderosa download "https://flirtingwithmodels.libsyn.com/rss" -n 1 -o downloads

# Transcribe a downloaded episode
uv run ponderosa transcribe downloads/some_episode.mp3
```

## CLI Commands

### `parse-feed` - Parse an RSS feed

```bash
uv run ponderosa parse-feed <feed_url> [options]
```

| Option | Description |
|--------|-------------|
| `-n`, `--max-episodes` | Max episodes to parse (default: 10) |
| `-o`, `--output` | Save feed data as JSON |

### `download` - Download episodes from a feed

```bash
uv run ponderosa download <feed_url> [options]
```

| Option | Description |
|--------|-------------|
| `-n`, `--max-episodes` | Max episodes to download (default: 5) |
| `-o`, `--output` | Output directory (default: `./downloads`) |
| `-f`, `--force` | Re-download existing files |

### `transcribe` - Transcribe a local audio file

```bash
uv run ponderosa transcribe <audio_file> [options]
```

| Option | Description |
|--------|-------------|
| `-m`, `--model` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large-v3` (default: `base`) |
| `-o`, `--output` | Output path for transcript JSON (default: `<audio_file>.transcript.json`) |

The transcript JSON includes the full text, timestamped segments, detected language, and duration.

## Configuration

Configuration is loaded from environment variables or a `.env` file. See [.env.example](.env.example) for all options.

### Whisper Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPER_MODEL_SIZE` | `base` | Model size (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `WHISPER_DEVICE` | `cpu` | Device (`cpu` or `cuda`) |
| `WHISPER_COMPUTE_TYPE` | `int8` | Compute type (`int8`, `float16`, `float32`) |
| `WHISPER_LANGUAGE` | `en` | Language code |

### Podcast Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `PODCAST_MAX_EPISODES_PER_FEED` | `10` | Max episodes per feed |
| `PODCAST_SKIP_EXISTING` | `true` | Skip already-downloaded episodes |

## Project Structure

```
ponderosa/
├── src/ponderosa/
│   ├── config.py           # Configuration management
│   ├── cli.py              # Command-line interface
│   ├── logging.py          # Structured logging setup
│   ├── ingestion/          # RSS parsing & audio download
│   ├── transcription/      # faster-whisper transcription
│   ├── enrichment/         # Summarization (planned)
│   ├── storage/            # Storage utilities (planned)
│   └── search/             # Semantic search (planned)
├── tests/                  # Test suite
└── docs/                   # Documentation
```

## Development

```bash
# Run tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run linter
uv run ruff check .

# Format code
uv run ruff format .
```

## License

MIT
