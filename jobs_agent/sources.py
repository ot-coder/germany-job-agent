from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import sys
from typing import Callable
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from .config import DEFAULT_PROFILE, DEFAULT_QUERIES, Profile
from .core import IRRELEVANT, Job, plain_text, score_job, stable_job_id

# The default profile's curated Bundesagentur searches (see config.py).
BA_QUERIES = DEFAULT_QUERIES


USER_AGENT = "Mozilla/5.0 (compatible; GermanyJobAgent/0.2; +https://github.com/ot-coder/germany-job-agent)"


def is_local(location: str, profile: Profile = DEFAULT_PROFILE) -> bool:
    """True when the posting's town is the configured city or a listed nearby town."""
    town = location.split(",", 1)[0].strip().casefold()
    return town in profile.local_towns()


def normalize_arbeitnow(raw: dict, profile: Profile = DEFAULT_PROFILE) -> Job:
    title = str(raw.get("title", "")).strip()
    company = str(raw.get("company_name", "Unknown")).strip()
    location = str(raw.get("location", "Germany")).strip() or "Germany"
    description = plain_text(str(raw.get("description", "")))
    created = raw.get("created_at")
    published_at = ""
    if isinstance(created, (int, float)):
        published_at = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()
    job = Job(
        id=stable_job_id(company, title, location),
        title=title,
        company=company,
        location=location,
        url=str(raw.get("url", "")),
        description=description,
        source="arbeitnow",
        remote=bool(raw.get("remote", False)),
        published_at=published_at,
    )
    job.score, job.reasons = score_job(job, profile)
    return job


def _display_location(value: object) -> str:
    return str(value or "").strip().replace("_", " ").title()


def normalize_ba(raw: dict, profile: Profile = DEFAULT_PROFILE) -> Job:
    title = str(raw.get("titel") or raw.get("stellenangebotsTitel") or "").strip()
    company = str(raw.get("arbeitgeber") or raw.get("firma") or "Unknown").strip()
    place = raw.get("arbeitsort") or {}
    locations = raw.get("stellenlokationen") or []
    if not place and locations and isinstance(locations[0], dict):
        place = locations[0].get("adresse") or {}
    location = ", ".join(
        _display_location(place.get(key)) for key in ("ort", "region", "land") if place.get(key)
    )
    description = plain_text(str(raw.get("beruf") or raw.get("hauptberuf") or ""))
    reference = str(raw.get("refnr") or raw.get("referenznummer") or "").strip()
    job = Job(
        id=stable_job_id(company, title, location), title=title, company=company,
        location=location or "Deutschland",
        url=f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{reference}",
        description=description, source="bundesagentur",
        published_at=str(
            raw.get("aktuelleVeroeffentlichungsdatum")
            or raw.get("datumErsteVeroeffentlichung")
            or ""
        ),
    )
    job.score, job.reasons = score_job(job, profile)
    return job


def normalize_remotive(raw: dict, profile: Profile = DEFAULT_PROFILE) -> Job:
    title = str(raw.get("title", "")).strip()
    company = str(raw.get("company_name", "Unknown")).strip()
    location = str(raw.get("candidate_required_location", "Remote")).strip() or "Remote"
    description = plain_text(str(raw.get("description", "")))
    job = Job(
        id=stable_job_id(company, title, location), title=title, company=company,
        location=location, url=str(raw.get("url", "")), description=description,
        source="remotive", remote=True,
        published_at=str(raw.get("publication_date", "")),
    )
    job.score, job.reasons = score_job(job, profile)
    return job


class _BAStateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_state = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("id") == "ng-state":
            self.in_state = True

    def handle_data(self, data: str) -> None:
        if self.in_state:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_state:
            self.in_state = False


def _parse_ba_search_html(html: str) -> dict:
    parser = _BAStateParser()
    parser.feed(html)
    if not parser.parts:
        raise ValueError("Bundesagentur search page did not contain ng-state data")
    state = json.loads("".join(parser.parts))
    search = state.get("suchergebnis") or {}
    jobs = search.get("ergebnisliste") or []
    if not isinstance(jobs, list):
        raise ValueError("Bundesagentur ng-state search results are invalid")
    return {"stellenangebote": jobs}


def _fetch_json(url: str) -> dict:
    is_ba_page = "www.arbeitsagentur.de/jobsuche/suche" in url
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html" if is_ba_page else "application/json",
    }
    if "rest.arbeitsagentur.de" in url:
        headers["X-API-Key"] = "jobboerse-jobsuche"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        if is_ba_page:
            return _parse_ba_search_html(response.read().decode("utf-8"))
        return json.load(response)


def _ba_search_url(query: str, location_query: str) -> str:
    return (
        "https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=1"
        f"&was={quote_plus(query)}&{location_query}"
    )


@dataclass(slots=True)
class FetchResult:
    """Stats travel alongside the passing job list so notifications can say
    how much was evaluated without re-fetching or re-scoring."""

    jobs: list[Job] = field(default_factory=list)
    evaluated: int = 0
    duplicates_removed: int = 0
    passed_threshold: int = 0


def fetch_all(
    fetch_json: Callable[[str], dict] = _fetch_json,
    min_score: int | None = None,
    profile: Profile = DEFAULT_PROFILE,
) -> FetchResult:
    threshold = profile.min_score if min_score is None else min_score
    candidates: list[Job] = []
    radius_ids: set[str] = set()
    successful_requests = 0
    failures: list[str] = []

    def load(source: str, url: str) -> dict | None:
        nonlocal successful_requests
        try:
            result = fetch_json(url)
        except Exception as error:
            failures.append(f"{source}: {error}")
            return None
        successful_requests += 1
        return result

    arbeitnow = load("arbeitnow", "https://www.arbeitnow.com/api/job-board-api")
    if arbeitnow is not None:
        candidates.extend(normalize_arbeitnow(item, profile) for item in arbeitnow.get("data", []))

    if profile.include_remote:
        remotive = load("remotive", "https://remotive.com/api/remote-jobs")
        if remotive is not None:
            candidates.extend(normalize_remotive(item, profile) for item in remotive.get("jobs", []))

    local_query = f"wo={quote_plus(profile.city)}&umkreis={profile.radius_km}"
    searches = [
        (query, category.scope == "local")
        for category in profile.categories
        for query in category.queries
    ]
    for query, local in searches:
        result = load("bundesagentur", _ba_search_url(query, local_query if local else "wo=Deutschland"))
        if result is None:
            break
        for item in result.get("stellenangebote", []):
            job = normalize_ba(item, profile)
            if local:
                radius_ids.add(job.id)
            candidates.append(job)

    for failure in failures:
        print(f"Warning: job source unavailable: {failure}", file=sys.stderr)
    if successful_requests == 0:
        raise RuntimeError("All job sources failed; refusing to publish an empty dashboard")

    # Dedupe across all sources BEFORE the threshold, keeping the best-scoring
    # variant, so a thin listing never beats a richer copy of the same job.
    evaluated = len(candidates)
    best: dict[str, Job] = {}
    for job in candidates:
        existing = best.get(job.id)
        if existing is None or job.score > existing.score:
            best[job.id] = job
    duplicates_removed = evaluated - len(best)

    # With an explicit nearby-town list, only those towns count as local. Without
    # one, trust Bundesagentur's own radius search plus exact city matches.
    strict_towns = bool(profile.nearby_towns)

    def in_area(job: Job) -> bool:
        category = profile.category(job.category)
        if category is None or category.scope != "local":
            return True
        return is_local(job.location, profile) or (not strict_towns and job.id in radius_ids)

    passing = [
        job for job in best.values()
        if job.role_family != IRRELEVANT and job.score >= threshold and in_area(job)
    ]
    passing.sort(key=lambda job: (-job.score, job.title.casefold()))
    return FetchResult(
        jobs=passing, evaluated=evaluated,
        duplicates_removed=duplicates_removed, passed_threshold=len(passing),
    )
