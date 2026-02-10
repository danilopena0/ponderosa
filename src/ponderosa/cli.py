"""Command-line interface for Ponderosa.

Provides commands for testing and running pipeline components locally.
"""

import argparse
import json
import sys
from pathlib import Path

from ponderosa.config import get_settings
from ponderosa.ingestion import AudioDownloader, RSSParser
from ponderosa.logging import setup_logging


def cmd_parse_feed(args: argparse.Namespace) -> int:
    """Parse an RSS feed and display episode information."""
    setup_logging(log_level="INFO")

    parser = RSSParser(max_episodes=args.max_episodes)
    feed = parser.parse_feed(args.feed_url)

    print(f"\nPodcast: {feed.title}")
    print(f"Author: {feed.author}")
    print(f"Episodes found: {len(feed.episodes)}\n")

    for i, ep in enumerate(feed.episodes, 1):
        duration = f"{ep.duration_seconds // 60}m" if ep.duration_seconds else "N/A"
        print(f"{i}. {ep.title}")
        print(f"   Published: {ep.published_at}")
        print(f"   Duration: {duration}")
        print(f"   Audio: {ep.audio_url}")
        print()

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(
            json.dumps(feed.model_dump(mode="json"), indent=2, default=str)
        )
        print(f"Saved feed data to: {output_path}")

    return 0


def cmd_download(args: argparse.Namespace) -> int:
    """Download episodes from a feed."""
    setup_logging(log_level="INFO")

    parser = RSSParser(max_episodes=args.max_episodes)
    feed = parser.parse_feed(args.feed_url)

    print(f"\nPodcast: {feed.title}")
    print(f"Episodes to download: {len(feed.episodes)}\n")

    downloader = AudioDownloader()

    dest_dir = Path(args.output) if args.output else Path("./downloads")
    dest_dir.mkdir(parents=True, exist_ok=True)

    results = downloader.download_feed(
        feed,
        local_dir=dest_dir,
        skip_existing=not args.force,
    )

    print(f"\nDownloaded {len(results)} episodes")
    for ep_id, path in results.items():
        print(f"  {ep_id}: {path}")

    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    """Transcribe a local audio file."""
    setup_logging(log_level="INFO")
    settings = get_settings()

    audio_path = Path(args.audio_file)
    if not audio_path.exists():
        print(f"Error: File not found: {audio_path}")
        return 1

    from ponderosa.transcription import Transcriber

    model_size = args.model or settings.whisper.model_size
    transcriber = Transcriber(
        model_size=model_size,
        device=settings.whisper.device,
        compute_type=settings.whisper.compute_type,
        language=settings.whisper.language,
    )

    print(f"\nTranscribing: {audio_path}")
    print(f"Model: {model_size}\n")

    result = transcriber.transcribe(audio_path)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = audio_path.with_suffix(".transcript.json")

    output_path.write_text(
        json.dumps(result.model_dump(), indent=2, default=str)
    )

    print(f"Language: {result.language}")
    print(f"Duration: {result.duration:.1f}s")
    print(f"Segments: {len(result.segments)}")
    print(f"\nTranscript saved to: {output_path}")

    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="ponderosa",
        description="Podcast Intelligence Pipeline - Local transcription and enrichment",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # parse-feed command
    parse_parser = subparsers.add_parser("parse-feed", help="Parse an RSS feed")
    parse_parser.add_argument("feed_url", help="RSS feed URL")
    parse_parser.add_argument(
        "--max-episodes", "-n", type=int, default=10, help="Max episodes to parse"
    )
    parse_parser.add_argument("--output", "-o", help="Output JSON file path")
    parse_parser.set_defaults(func=cmd_parse_feed)

    # download command
    dl_parser = subparsers.add_parser("download", help="Download episodes from a feed")
    dl_parser.add_argument("feed_url", help="RSS feed URL")
    dl_parser.add_argument(
        "--max-episodes", "-n", type=int, default=5, help="Max episodes to download"
    )
    dl_parser.add_argument("--output", "-o", help="Output directory")
    dl_parser.add_argument(
        "--force", "-f", action="store_true", help="Re-download existing files"
    )
    dl_parser.set_defaults(func=cmd_download)

    # transcribe command
    tr_parser = subparsers.add_parser("transcribe", help="Transcribe a local audio file")
    tr_parser.add_argument("audio_file", help="Path to audio file (mp3, wav, etc.)")
    tr_parser.add_argument("--model", "-m", help="Whisper model size (tiny, base, small, medium, large-v3)")
    tr_parser.add_argument("--output", "-o", help="Output path for transcript JSON")
    tr_parser.set_defaults(func=cmd_transcribe)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
