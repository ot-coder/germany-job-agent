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


def notify_tier(score: int) -> tuple[str, str]:
    """Maps a score to (tier, emoji). Thresholds are a ranking convenience,
    not a scientific probability — see guides/ranking.md."""
    if score >= 90:
        return "EXCEPTIONAL", "🌟"
    if score >= 82:
        return "APPLY", "✅"
    if score >= 75:
        return "REVIEW", "👀"
    return "SILENT", ""


def notification_worthy(new_jobs: list[Job], profile: Profile = DEFAULT_PROFILE, cap: int | None = None) -> list[Job]:
    """Anti-spam rule shared by Telegram and the GitHub digest.

    Only genuinely new jobs (not previously published) that reach the notify
    threshold are eligible, highest score first, capped. Jobs that miss the
    cap or the threshold are still on the dashboard; they are never surfaced
    later, because publish_jobs() marks them as known once written.
    """
    limit = profile.notify_limit if cap is None else cap
    ranked = sorted(new_jobs, key=lambda job: -job.score)
    return [job for job in ranked if job.score >= profile.notify_min_score][:limit]


def _summary(evaluated: int, new: int, duplicates_removed: int, passed_threshold: int, surfaced: int) -> str:
    return (
        f"{evaluated} jobs evaluated · {new} new · "
        f"{duplicates_removed} duplicates removed · {passed_threshold} passed threshold · "
        f"{surfaced} surfaced"
    )


def telegram_message(
    new_jobs: list[Job],
    evaluated: int,
    duplicates_removed: int,
    passed_threshold: int,
    site_url: str,
    cap: int | None = None,
    profile: Profile = DEFAULT_PROFILE,
) -> str:
    """Concise morning briefing. Empty when nothing new clears the threshold."""
    worthy = notification_worthy(new_jobs, profile, cap)
    if not worthy:
        return ""
    noun = "role" if len(worthy) == 1 else "roles"
    lines = [f"{profile.title}: {len(worthy)} new suitable {noun}", ""]
    for job in worthy:
        tier, emoji = notify_tier(job.score)
        lines.append(f"{emoji} {tier} ({job.score}/100) — {job.title}")
        lines.append(f"   {job.company} · {job.location} · {profile.family_label(job.role_family)}")
        if job.reasons:
            lines.append(f"   Why: {'; '.join(job.reasons[:2])}")
        lines.append(f"   {job.url}")
        lines.append("")
    lines.append(f"Open dashboard: {site_url}")
    lines.append(_summary(evaluated, len(new_jobs), duplicates_removed, passed_threshold, len(worthy)))
    return "\n".join(lines)


def _md(text: str) -> str:
    """Neutralise characters that would turn job text into Markdown/HTML or @mentions."""
    for char in "\\`*_[]<>|#@":
        text = text.replace(char, "\\" + char)
    return text


def digest_markdown(
    new_jobs: list[Job],
    evaluated: int,
    duplicates_removed: int,
    passed_threshold: int,
    site_url: str,
    total_jobs: int | None = None,
    profile: Profile = DEFAULT_PROFILE,
) -> str:
    """Body of the daily GitHub issue. Empty (no issue) when nothing qualifies."""
    worthy = notification_worthy(new_jobs, profile)
    if not worthy:
        return ""
    noun = "role" if len(worthy) == 1 else "roles"
    total = f" The dashboard has **{total_jobs}** live matches." if total_jobs is not None else ""
    lines = [f"**{len(worthy)} new suitable {noun}** today.{total} [Open dashboard]({site_url})", ""]
    many_categories = len(profile.categories) > 1
    for job in worthy:
        tier, emoji = notify_tier(job.score)
        url = job.url if job.url.startswith(("https://", "http://")) else site_url
        where = profile.category_label(job.category) + " · " if many_categories else ""
        lines.append(f"- {emoji} **{tier} {job.score}/100** — [{_md(job.title)}]({url})")
        lines.append(
            f"  {_md(job.company)} · {_md(job.location)} · {_md(where + profile.family_label(job.role_family))}"
        )
        if job.reasons:
            lines.append(f"  <sub>{_md('; '.join(job.reasons[:2]))}</sub>")
    remaining = len(new_jobs) - len(worthy)
    lines.append("")
    if remaining > 0:
        lines.append(f"{remaining} more new {'match' if remaining == 1 else 'matches'} below the alert threshold are on the dashboard.")
    lines.append(f"<sub>{_summary(evaluated, len(new_jobs), duplicates_removed, passed_threshold, len(worthy))}</sub>")
    return "\n".join(lines) + "\n"
