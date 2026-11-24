"""Turn a handful of answers (job field, city, level) into jobs-agent.toml.

Used by the "Set up my job agent" GitHub Actions form, and runnable locally:

    python3 -m jobs_agent setup --field "pflege, krankenpflege" --city Dresden --level any
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tomllib

from .config import CONFIG_FILENAME, DEFAULT_PROFILE, parse_config

LEVELS = {
    "student": {
        "levels": ["werkstudent", "internship", "entry-level", "part-time", "minijob"],
        "prefixes": ["werkstudent", "junior"],
    },
    "entry": {"levels": ["entry-level", "werkstudent", "internship"], "prefixes": ["junior", "berufseinsteiger"]},
    # "any" still rejects senior/lead/head-of roles; the score rewards junior framing.
    "any": {"levels": ["any"], "prefixes": [""]},
}
PART_TIME_LABEL = "Part-time & Minijob"
PART_TIME_LEVELS = ["werkstudent", "part-time", "minijob"]
PART_TIME_QUERIES = [
    "minijob", "teilzeit", "studentenjob", "aushilfe lager", "aushilfe gastronomie", "aushilfe restaurant",
]
MAX_TERMS = 6


def _q(value: object) -> str:
    """TOML basic strings share JSON's escape rules."""
    return json.dumps(value, ensure_ascii=False)


def _truthy(value: str | bool) -> bool:
    return value if isinstance(value, bool) else str(value).strip().casefold() in {"1", "true", "yes", "y", "on"}


def split_terms(field: str) -> list[str]:
    terms = []
    for raw in field.replace(";", ",").split(","):
        term = " ".join(raw.split()).casefold()
        if len(term) >= 2 and term not in terms:
            terms.append(term)
    return terms[:MAX_TERMS]


def build_config(
    field: str,
    city: str,
    radius_km: int = 35,
    level: str = "student",
    scope: str = "germany",
    local_part_time: bool = True,
    include_remote: bool = True,
    title: str = "",
) -> str:
    terms = split_terms(field)
    if not terms:
        raise ValueError("Enter at least one job field or keyword, e.g. 'software, entwickler'.")
    city = " ".join(city.split())
    if not city:
        raise ValueError("Enter your city, e.g. 'Leipzig'.")
    if level not in LEVELS:
        raise ValueError(f"level must be one of {', '.join(LEVELS)}")
    if scope not in ("germany", "local"):
        raise ValueError("scope must be 'germany' or 'local'")
    if not 1 <= radius_km <= 200:
        raise ValueError("radius_km must be between 1 and 200")

    spec = LEVELS[level]
    queries = [f"{prefix} {term}".strip() for term in terms for prefix in spec["prefixes"]]
    label = ", ".join(t.title() for t in terms[:3])
    title = title.strip() or f"{label} jobs · {city}"

    lines = [
        "# Germany Job Agent configuration.",
        "# Re-run the \"Set up my job agent\" workflow, or edit this file by hand.",
        "# Reference: https://github.com/ot-coder/germany-job-agent#configuration",
        "",
        "[profile]",
        f"title = {_q(title)}",
        f"city = {_q(city)}",
        f"radius_km = {radius_km}",
        "# Leave empty to trust the Bundesagentur radius search; list towns to restrict 'local' tabs to them.",
        "nearby_towns = []",
        "# 0-100. Jobs below min_score are hidden; new jobs at notify_min_score or above",
        "# (at most notify_limit per day) are sent as your daily notification.",
        f"min_score = {DEFAULT_PROFILE.min_score}",
        f"notify_min_score = {DEFAULT_PROFILE.notify_min_score}",
        f"notify_limit = {DEFAULT_PROFILE.notify_limit}",
        f"include_remote = {'true' if include_remote else 'false'}",
        "# Optional: your own Google OAuth client ID for Gmail auto-detection (see guides/gmail.md).",
        'gmail_client_id = ""',
        "",
        "[[categories]]",
        'id = "field"',
        f"label = {_q(label)}",
        f"scope = {_q(scope)}",
        "# A job title must contain one of these words to count as your field.",
        f"keywords = {_q(terms)}",
        f"levels = {_q(spec['levels'])}",
        "# Searches sent to the Bundesagentur für Arbeit job board.",
        f"queries = {_q(queries)}",
    ]
    if local_part_time:
        lines += [
            "",
            "[[categories]]",
            'id = "part-time"',
            f"label = {_q(PART_TIME_LABEL)}",
            'scope = "local"',
            "keywords = []",
            f"levels = {_q(PART_TIME_LEVELS)}",
            f"queries = {_q(PART_TIME_QUERIES)}",
        ]
    return "\n".join(lines) + "\n"


def add_setup_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--field", required=True, help="Comma-separated job field keywords, e.g. 'software, entwickler'")
    parser.add_argument("--city", required=True)
    parser.add_argument("--radius", type=int, default=35, help="Search radius in km for local tabs")
    parser.add_argument("--level", choices=sorted(LEVELS), default="student")
    parser.add_argument("--scope", choices=("germany", "local"), default="germany", help="Where to look for your field")
    parser.add_argument("--local-part-time", default="true", help="Also list part-time/minijobs near your city (true/false)")
    parser.add_argument("--remote", default="true", help="Include remote jobs from Remotive (true/false)")
    parser.add_argument("--title", default="")
    parser.add_argument("--output", type=Path, default=Path(CONFIG_FILENAME))


def run_setup(args: argparse.Namespace) -> Path:
    text = build_config(
        field=args.field, city=args.city, radius_km=args.radius, level=args.level, scope=args.scope,
        local_part_time=_truthy(args.local_part_time), include_remote=_truthy(args.remote), title=args.title,
    )
    parse_config(tomllib.loads(text))  # refuse to write a file the agent cannot read
    args.output.write_text(text, encoding="utf-8")
    return args.output
