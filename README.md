# Ponderosa - Podcast Intelligence Pipeline

A local-first pipeline for podcast transcription, enrichment, and semantic search.

## Overview

Ponderosa processes podcasts through a complete pipeline — all running locally with no cloud dependencies:

1. **Ingestion** - Parse RSS feeds and download audio locally
2. **Transcription** - Convert audio to text using faster-whisper (local Whisper)
3. **Enrichment** - Extract themes, learnings, and strategies via Perplexity API
4. **Storage** - Semantic vector storage with ChromaDB
5. **Search** - Semantic search via CLI or FastAPI API

## Demo


https://github.com/user-attachments/assets/cf5f13a2-f6fd-4f0b-beb8-9d1f78f61490



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

### `enrich` - Extract insights from a transcript

```bash
uv run ponderosa enrich <transcript.json> [options]
```

| Option | Description |
|--------|-------------|
| `-o`, `--output` | Save enrichment JSON to file |

### `episodes` - List all enriched episodes

```bash
uv run ponderosa episodes
```

Shows all episodes stored in ChromaDB with their IDs, titles, and insight counts.

### `episode` - Show details for an episode and export to markdown

```bash
uv run ponderosa episode <episode_id> [options]
```

| Option | Description |
|--------|-------------|
| `-o`, `--output` | Output markdown file path (default: `<episode_id>.md`) |

Generates a markdown file with the episode's summary, themes, learnings, and strategies.

### `search` - Search enriched podcast data

```bash
uv run ponderosa search <query> [options]
```

| Option | Description |
|--------|-------------|
| `-l`, `--limit` | Max results per category (default: 10) |

### `serve` - Start the FastAPI search API

```bash
uv run ponderosa serve [options]
```

| Option | Description |
|--------|-------------|
| `--host` | Host to bind (default: `127.0.0.1`) |
| `-p`, `--port` | Port (default: `8000`) |
| `--reload` | Enable auto-reload for development |

API endpoints:
- `GET /episodes` — list all enriched episodes
- `GET /episodes/{id}` — full enrichment for an episode
- `GET /search?q=...&limit=10` — search across all collections
- `GET /search/themes?q=...` — search themes
- `GET /search/learnings?q=...` — search learnings
- `GET /search/strategies?q=...` — search strategies

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
│   ├── enrichment/         # Perplexity-based insight extraction
│   ├── storage/            # ChromaDB vector storage
│   ├── api.py              # FastAPI search API
│   └── search/             # Search utilities
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
