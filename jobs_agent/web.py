from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def render_digest(jobs: list[dict], new_count: int, limit: int = 10) -> str:
    noun = "role" if new_count == 1 else "roles"
    lines = [f"## Germany Job Agent Digest — {new_count} new suitable {noun}", ""]
    if not jobs:
        return "\n".join(lines + ["No suitable roles are currently stored."])
    for index, job in enumerate(jobs[:limit], 1):
        lines.append(f"{index}. **[{job['title']}]({job['url']})** — {job['company']}")
        lines.append(f"   {job['location']} · {job['role_family']} · **{job['score']}/100** · {', '.join(job['reasons'])}")
    lines.extend(["", "Open the local dashboard with: `python3 -m jobs_agent serve`"])
    return "\n".join(lines)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def serve(docs_dir: str | Path, host: str = "127.0.0.1", port: int = 8787) -> None:
    """Serve the built static dashboard (the same files GitHub Pages serves)."""
    handler = partial(_QuietHandler, directory=str(Path(docs_dir).resolve()))
    print(f"Dashboard: http://{host}:{port}/  (Ctrl+C to stop)")
    try:
        ThreadingHTTPServer((host, port), handler).serve_forever()
    except KeyboardInterrupt:
        pass
