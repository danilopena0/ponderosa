# Ponderosa - Podcast Intelligence Pipeline

A production-grade MLOps pipeline for podcast transcription, enrichment, and semantic search using Vertex AI.

## Overview

Ponderosa demonstrates deep Vertex AI expertise through a complete podcast processing pipeline:

1. **Ingestion** - Parse RSS feeds and download audio to Cloud Storage
2. **Transcription** - Convert audio to text using Speech-to-Text (Chirp 3)
3. **Enrichment** - Summarize and extract topics using Gemini
4. **Search** - Semantic search via Vertex AI Vector Search
5. **API** - FastAPI interface deployed on Cloud Run

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Google Cloud account ([$300 free credits](https://cloud.google.com/free))

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/ponderosa.git
cd ponderosa

# Install dependencies
make install-dev

# Copy environment template
cp .env.example .env
# Edit .env with your GCP settings
```

### Test RSS Parser (No GCP Required)

```bash
# Parse a podcast feed
make run-parser

# Or directly:
uv run ponderosa parse-feed "https://flirtingwithmodels.libsyn.com/rss"
```

### Download Episodes Locally

```bash
# Download 1 episode to ./downloads
make run-download

# Or with options:
uv run ponderosa download "https://flirtingwithmodels.libsyn.com/rss" -n 3 -o ./my-podcasts
```

## GCP Setup

See [docs/GCP_SETUP.md](docs/GCP_SETUP.md) for detailed instructions on:
- Creating a GCP project with free credits
- Enabling required APIs
- Setting up authentication
- Configuring billing alerts

## Project Structure

```
ponderosa/
├── src/ponderosa/
│   ├── config.py           # Configuration management
│   ├── cli.py              # Command-line interface
│   ├── logging.py          # Structured logging setup
│   ├── ingestion/          # RSS parsing & audio download
│   ├── transcription/      # Speech-to-Text integration
│   ├── enrichment/         # Gemini summarization
│   ├── storage/            # GCS & BigQuery clients
│   └── search/             # Vector search
├── pipelines/              # Vertex AI Pipeline definitions
├── api/                    # FastAPI application
├── tests/                  # Test suite
└── docs/                   # Documentation
```

## Development

```bash
# Run tests
make test

# Run linter
make lint

# Format code
make format

# Type checking
make typecheck

# Run all checks
make check
```

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   RSS Feed   │───▶│   Cloud      │───▶│  Speech-to-  │
│   Parser     │    │   Storage    │    │  Text API    │
└──────────────┘    └──────────────┘    └──────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────┐
                    ▼                          ▼                      ▼
             ┌──────────────┐          ┌──────────────┐       ┌──────────────┐
             │  Gemini API  │          │  Embedding   │       │   BigQuery   │
             │  Summarize   │          │  Generation  │       │   Metadata   │
             └──────────────┘          └──────────────┘       └──────────────┘
                    │                          │
                    └────────────┬─────────────┘
                                 ▼
                          ┌──────────────┐
                          │  Vertex AI   │
                          │  Vector      │
                          │  Search      │
                          └──────────────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │  FastAPI     │
                          │  (Cloud Run) │
                          └──────────────┘
```

## Cost Optimization

| Service | Free Tier | Batch Rate | Strategy |
|---------|-----------|------------|----------|
| Speech-to-Text | 60 min/month | $0.004/min | Use batch mode |
| Vertex AI Pipelines | Free (preview) | - | No cost |
| Cloud Storage | 5 GB | $0.020/GB | Minimal |
| Gemini Flash | Free tier | Per token | Use Flash not Pro |

**Tips:**
- Set billing alerts at $50, $100, $200
- Undeploy Vector Search endpoints when not demoing
- Use batch mode for transcription (75% cheaper)

## License

MIT
