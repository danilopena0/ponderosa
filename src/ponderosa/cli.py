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


def cmd_enrich(args: argparse.Namespace) -> int:
    """Enrich a transcript and store in ChromaDB."""
    setup_logging(log_level="INFO")

    from ponderosa.enrichment import Enricher
    from ponderosa.storage import PonderosaStore

    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        print(f"Error: File not found: {transcript_path}")
        return 1

    print(f"\nEnriching: {transcript_path}")

    enricher = Enricher()
    result = enricher.enrich_transcript(transcript_path)

    # Use filename stem as episode ID
    episode_id = transcript_path.stem.replace(".transcript", "")

    from ponderosa.storage import PonderosaStore, make_short_id

    store = PonderosaStore()
    store.store_enrichment(episode_id, result)

    short_id = make_short_id(episode_id)
    print(f"\nEpisode: {result.episode_title}")
    print(f"ID:      {short_id}")
    print(f"Themes: {len(result.themes)}")
    print(f"Learnings: {len(result.learnings)}")
    print(f"Strategies: {len(result.strategies)}")

    # Optionally save enrichment JSON
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(result.model_dump(), indent=2))
        print(f"Enrichment saved to: {output_path}")

    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the FastAPI server."""
    import uvicorn

    host = args.host
    port = args.port
    print(f"\nStarting Ponderosa API on {host}:{port}")
    uvicorn.run("ponderosa.api:app", host=host, port=port, reload=args.reload)
    return 0


def cmd_episodes(args: argparse.Namespace) -> int:
    """List all enriched episodes."""
    setup_logging(log_level="WARNING")

    from ponderosa.storage import PonderosaStore

    store = PonderosaStore()
    episodes = store.list_episodes()

    if not episodes:
        print("\nNo enriched episodes found.")
        print("Run: ponderosa enrich <transcript.json>")
        return 0

    print(f"\n{'=' * 60}")
    print(f"  ENRICHED EPISODES ({len(episodes)})")
    print(f"{'=' * 60}")
    for ep in episodes:
        short = ep.get("short_id", "N/A")
        print(f"\n  ID:         {short}")
        print(f"  Full ID:    {ep['id']}")
        print(f"  Title:      {ep.get('episode_title', 'N/A')}")
        print(f"  Themes:     {ep.get('themes_count', 0)}")
        print(f"  Learnings:  {ep.get('learnings_count', 0)}")
        print(f"  Strategies: {ep.get('strategies_count', 0)}")

    return 0


def cmd_episode(args: argparse.Namespace) -> int:
    """Show full details for an enriched episode."""
    setup_logging(log_level="WARNING")

    from ponderosa.storage import PonderosaStore

    store = PonderosaStore()
    episode = store.get_episode(args.episode_id)

    if not episode:
        print(f"\nEpisode not found: {args.episode_id}")
        print("Run: ponderosa episodes  (to see available IDs)")
        return 1

    title = episode.get('episode_title', episode['id'])

    # Build markdown
    lines = [f"# {title}", "", f"**Episode ID:** {episode['id']}", ""]
    lines += ["## Summary", "", episode.get("summary", "N/A"), ""]

    for category in ("themes", "learnings", "strategies"):
        items = episode.get(category, [])
        if items:
            lines += [f"## {category.title()} ({len(items)})", ""]
            for item in items:
                name = item.get("name", "N/A")
                doc = item.get("document", "")
                keywords = item.get("keywords", "")
                score = item.get("relevance_score", "")
                desc = ""
                if doc:
                    desc = doc.split(": ", 1)[1] if ": " in doc else doc
                lines.append(f"### {name}")
                if score:
                    lines.append(f"**Relevance:** {score}")
                if desc:
                    lines.append(f"\n{desc}")
                if keywords:
                    lines.append(f"\n*Keywords: {keywords}*")
                lines.append("")

    md_content = "\n".join(lines)

    # Output to file or stdout
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(f"{args.episode_id}.md")

    output_path.write_text(md_content)
    print(f"Saved to: {output_path}")

    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """Search across all enriched data."""
    setup_logging(log_level="WARNING")

    from ponderosa.storage import PonderosaStore

    store = PonderosaStore()
    results = store.search_all(args.query, limit=args.limit)

    for category, items in results.items():
        if items:
            print(f"\n{'=' * 60}")
            print(f"  {category.upper()}")
            print(f"{'=' * 60}")
            for item in items:
                score = 1 - item.get("distance", 1)
                print(f"\n  [{score:.2f}] {item.get('name', 'N/A')}")
                print(f"         {item['document']}")
                ep = item.get("episode_title", "")
                if ep:
                    print(f"         Episode: {ep}")

    total = sum(len(v) for v in results.values())
    if total == 0:
        print("\nNo results found.")
    else:
        print(f"\n{total} results found.")

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

    # enrich command
    en_parser = subparsers.add_parser("enrich", help="Enrich a transcript and store in ChromaDB")
    en_parser.add_argument("transcript", help="Path to transcript JSON file")
    en_parser.add_argument("--output", "-o", help="Save enrichment JSON to file")
    en_parser.set_defaults(func=cmd_enrich)

    # episodes command
    ep_list_parser = subparsers.add_parser("episodes", help="List all enriched episodes")
    ep_list_parser.set_defaults(func=cmd_episodes)

    # episode command
    ep_parser = subparsers.add_parser("episode", help="Show details for an enriched episode")
    ep_parser.add_argument("episode_id", help="Episode ID (run 'ponderosa episodes' to see IDs)")
    ep_parser.add_argument("--output", "-o", help="Output markdown file path (default: <episode_id>.md)")
    ep_parser.set_defaults(func=cmd_episode)

    # serve command
    sv_parser = subparsers.add_parser("serve", help="Start the FastAPI search API")
    sv_parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    sv_parser.add_argument("--port", "-p", type=int, default=8000, help="Port (default: 8000)")
    sv_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    sv_parser.set_defaults(func=cmd_serve)

    # search command
    sr_parser = subparsers.add_parser("search", help="Search enriched podcast data")
    sr_parser.add_argument("query", help="Search query")
    sr_parser.add_argument("--limit", "-l", type=int, default=10, help="Max results per category")
    sr_parser.set_defaults(func=cmd_search)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
