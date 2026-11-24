from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import shutil

from .config import DEFAULT_PROFILE, Profile
from .core import Job


SITE_DIR = Path(__file__).parent / "site"
SITE_FILES = ("index.html", "app.js", "gmail.js", "styles.css")


def _load_previous(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {str(item.get("id")): item for item in value if isinstance(item, dict) and item.get("id")}


def publish_jobs(
    jobs: list[Job], docs_dir: str | Path, profile: Profile = DEFAULT_PROFILE
) -> list[Job]:
    docs = Path(docs_dir)
    docs.mkdir(parents=True, exist_ok=True)
    jobs_path = docs / "jobs.json"
    previous = _load_previous(jobs_path)
    exported = []
    new_jobs = []
    for job in jobs:
        item = asdict(job)
        if job.id in previous:
            item["first_seen_at"] = previous[job.id].get("first_seen_at", item["first_seen_at"])
        else:
            new_jobs.append(job)
        exported.append(item)
    exported.sort(key=lambda item: (-int(item["score"]), item["title"].casefold()))
    jobs_path.write_text(json.dumps(exported, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name in SITE_FILES:
        shutil.copyfile(SITE_DIR / name, docs / name)
    (docs / "config.json").write_text(
        json.dumps(profile.public(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (docs / ".nojekyll").write_text("", encoding="utf-8")
    return new_jobs


def telegram_message(
    new_jobs: list[Job],
    site_url: str,
    limit: int = 8,
    total_jobs: int | None = None,
    profile: Profile = DEFAULT_PROFILE,
) -> str:
    if not new_jobs:
        lines = [f"✅ {profile.title}: Daily scan complete", "", "No new suitable roles today."]
        if total_jobs is not None:
            noun = "match" if total_jobs == 1 else "matches"
            lines.append(f"The dashboard currently has {total_jobs} live {noun}.")
        lines.extend(["", f"Open dashboard: {site_url}"])
        return "\n".join(lines)
    noun = "role" if len(new_jobs) == 1 else "roles"
    lines = [f"{profile.title}: {len(new_jobs)} new suitable {noun}", ""]
    for job in new_jobs[:limit]:
        lines.extend([
            f"• {job.title}",
            f"  {profile.category_label(job.category)} · {job.company} · {job.location} · {job.score}/100",
            f"  {job.url}",
            "",
        ])
    if len(new_jobs) > limit:
        lines.append(f"+ {len(new_jobs) - limit} more")
    lines.append(f"Open dashboard: {site_url}")
    return "\n".join(lines)


def _md(text: str) -> str:
    """Neutralise characters that would turn job text into Markdown/HTML or @mentions."""
    for char in "\\`*_[]<>|#@":
        text = text.replace(char, "\\" + char)
    return text


def digest_markdown(
    new_jobs: list[Job],
    site_url: str,
    limit: int = 25,
    total_jobs: int | None = None,
    profile: Profile = DEFAULT_PROFILE,
) -> str:
    """Body of the daily GitHub issue that notifies the repository owner."""
    total = f" The dashboard has **{total_jobs}** live matches." if total_jobs is not None else ""
    if not new_jobs:
        return f"✅ Daily scan complete — no new suitable roles today.{total}\n\n[Open dashboard]({site_url})\n"
    noun = "role" if len(new_jobs) == 1 else "roles"
    lines = [f"**{len(new_jobs)} new suitable {noun}** today.{total} [Open dashboard]({site_url})", ""]
    by_category: dict[str, list[Job]] = {}
    for job in new_jobs[:limit]:
        by_category.setdefault(job.category, []).append(job)
    for category_id, jobs in by_category.items():
        lines.extend([f"### {_md(profile.category_label(category_id))}", ""])
        for job in jobs:
            url = job.url if job.url.startswith(("https://", "http://")) else site_url
            lines.append(
                f"- [{_md(job.title)}]({url}) — {_md(job.company)} · {_md(job.location)} · {job.score}/100"
            )
        lines.append("")
    if len(new_jobs) > limit:
        lines.append(f"…and {len(new_jobs) - limit} more on the dashboard.")
    return "\n".join(lines) + "\n"
