from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Callable

from .config import DEFAULT_PROFILE, Profile, load_config
from .publish import digest_markdown, publish_jobs, telegram_message
from .setup import add_setup_arguments, run_setup
from .sources import FetchResult, fetch_all
from .store import JobStore
from .web import render_digest, serve


def default_db_path() -> Path:
    return Path(os.environ.get("JOBS_AGENT_DB", Path.cwd() / "data" / "jobs.db"))


def run_fetch(store: JobStore, fetcher: Callable[[], FetchResult] = fetch_all) -> tuple[int, str]:
    result = fetcher()
    new_count = store.upsert(result.jobs)
    return new_count, render_digest(store.list_jobs(limit=10), new_count)


def run_publish(
    fetcher: Callable[[], FetchResult],
    docs_dir: Path,
    message_path: Path,
    site_url: str,
    profile: Profile = DEFAULT_PROFILE,
    digest_path: Path | None = None,
) -> int:
    result = fetcher()
    new_jobs = publish_jobs(result.jobs, docs_dir, profile)
    stats = (result.evaluated, result.duplicates_removed, result.passed_threshold)
    config_path = Path(docs_dir) / "config.json"
    public = json.loads(config_path.read_text(encoding="utf-8"))
    public["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    config_path.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    message_path.parent.mkdir(parents=True, exist_ok=True)
    message_path.write_text(telegram_message(new_jobs, *stats, site_url, profile=profile), encoding="utf-8")
    if digest_path is not None:
        digest_path.parent.mkdir(parents=True, exist_ok=True)
        digest_path.write_text(
            digest_markdown(new_jobs, *stats, site_url, total_jobs=len(result.jobs), profile=profile),
            encoding="utf-8",
        )
    return len(new_jobs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Germany Job Agent")
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--config", type=Path, default=None, help="Path to jobs-agent.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("fetch", help="Search sources, store matches, and print a digest")
    subparsers.add_parser("digest", help="Print the current top matches without fetching")

    serve_parser = subparsers.add_parser("serve", help="Run the dashboard and tracker locally")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8787)
    serve_parser.add_argument("--docs", type=Path, default=Path("docs"))
    serve_parser.add_argument("--refresh", action="store_true", help="Fetch fresh jobs before serving")

    publish_parser = subparsers.add_parser("publish", help="Fetch jobs and build the static dashboard")
    publish_parser.add_argument("--docs", type=Path, default=Path("docs"))
    publish_parser.add_argument("--message", type=Path, default=Path(".out/telegram.txt"))
    publish_parser.add_argument("--digest", type=Path, default=Path(".out/digest.md"))
    publish_parser.add_argument("--site-url", default=os.environ.get("SITE_URL", "http://127.0.0.1:8787/"))

    setup_parser = subparsers.add_parser("setup", help="Write jobs-agent.toml from a few answers")
    add_setup_arguments(setup_parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "setup":
        path = run_setup(args)
        print(f"Wrote {path}")
        return 0
    profile = load_config(args.config)
    fetcher = lambda: fetch_all(profile=profile)  # noqa: E731
    if args.command == "fetch":
        _, digest = run_fetch(JobStore(args.db), fetcher)
        print(digest)
    elif args.command == "digest":
        print(render_digest(JobStore(args.db).list_jobs(limit=10), 0))
    elif args.command == "serve":
        if args.refresh or not (args.docs / "index.html").exists():
            url = f"http://{args.host}:{args.port}/"
            count = run_publish(fetcher, args.docs, Path(".out/telegram.txt"), url, profile)
            print(f"Fetched jobs ({count} new)")
        serve(args.docs, args.host, args.port)
    elif args.command == "publish":
        count = run_publish(fetcher, args.docs, args.message, args.site_url, profile, args.digest)
        print(f"Published live dashboard with {count} new suitable roles")
    return 0
