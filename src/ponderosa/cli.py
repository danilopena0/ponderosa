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
from ponderosa.storage import GCSClient


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
    settings = get_settings()

    parser = RSSParser(max_episodes=args.max_episodes)
    feed = parser.parse_feed(args.feed_url)

    print(f"\nPodcast: {feed.title}")
    print(f"Episodes to download: {len(feed.episodes)}\n")

    # Set up GCS client if configured
    gcs_client = None
    if args.upload and settings.gcp.bucket_name:
        gcs_client = GCSClient(
            bucket_name=settings.gcp.bucket_name,
            project_id=settings.gcp.project_id,
        )
        print(f"Uploading to: gs://{settings.gcp.bucket_name}/")

    # Set up downloader
    downloader = AudioDownloader(gcs_client=gcs_client)

    # Download to local directory
    dest_dir = Path(args.output) if args.output else Path("./downloads")
    dest_dir.mkdir(parents=True, exist_ok=True)

    results = downloader.download_feed(
        feed,
        local_dir=dest_dir,
        upload_to_gcs=args.upload and gcs_client is not None,
        skip_existing=not args.force,
    )

    print(f"\nDownloaded {len(results)} episodes")
    for ep_id, path in results.items():
        print(f"  {ep_id}: {path}")

    return 0


def cmd_list_bucket(args: argparse.Namespace) -> int:
    """List contents of the configured GCS bucket."""
    setup_logging(log_level="INFO")
    settings = get_settings()

    if not settings.gcp.bucket_name:
        print("Error: GCP_BUCKET_NAME not configured")
        return 1

    gcs_client = GCSClient(
        bucket_name=settings.gcp.bucket_name,
        project_id=settings.gcp.project_id,
    )

    blobs = gcs_client.list_blobs(prefix=args.prefix, max_results=args.max_results)

    print(f"\nBucket: gs://{settings.gcp.bucket_name}/")
    print(f"Prefix: {args.prefix or '(none)'}")
    print(f"Found {len(blobs)} objects:\n")

    for blob in blobs:
        print(f"  {blob}")

    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="ponderosa",
        description="Podcast Intelligence Pipeline - Vertex AI MLOps project",
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
    dl_parser.add_argument("--upload", "-u", action="store_true", help="Upload to GCS")
    dl_parser.add_argument(
        "--force", "-f", action="store_true", help="Re-download existing files"
    )
    dl_parser.set_defaults(func=cmd_download)

    # list-bucket command
    list_parser = subparsers.add_parser("list-bucket", help="List GCS bucket contents")
    list_parser.add_argument("--prefix", "-p", help="Filter by prefix")
    list_parser.add_argument("--max-results", "-n", type=int, default=100)
    list_parser.set_defaults(func=cmd_list_bucket)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
