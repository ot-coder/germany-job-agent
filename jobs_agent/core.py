from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re

from .config import DEFAULT_PROFILE, DEFAULT_TECH_KEYWORDS, Category, Profile


SENIOR_TERMS = ("senior", "lead ", "principal", "staff ", "manager", "head of", "director")
WERKSTUDENT_TERMS = ("werkstudent", "working student", "student assistant", "studentische hilfskraft")
ENTRY_TERMS = ("junior", "entry level", "entry-level", "graduate", "trainee", "berufseinsteiger")
MINIJOB_TERMS = ("minijob", "mini-job", "geringfügig", "556 euro", "520 euro")
PART_TIME_TERMS = (
    "teilzeit", "part time", "part-time", "aushilfe", "nebenjob", "studentenjob",
    "student job", "temporary staff",
)
TECH_TERMS = DEFAULT_TECH_KEYWORDS
GERMAN_CITIES = (
    "germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "cologne", "köln",
    "frankfurt", "stuttgart", "düsseldorf",
)


@dataclass(slots=True)
class Job:
    id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    source: str
    role_type: str = "other"
    category: str = "other"
    remote: bool = False
    published_at: str = ""
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    first_seen_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def stable_job_id(company: str, title: str, location: str) -> str:
    key = "|".join(_normalized(v) for v in (company, title, location))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def classify_role(title: str, description: str = "") -> str:
    title_text = _normalized(title)
    if any(term in title_text for term in SENIOR_TERMS):
        return "other"
    if any(term in title_text for term in WERKSTUDENT_TERMS):
        return "werkstudent"
    if any(term in title_text for term in ENTRY_TERMS):
        return "entry-level"
    if any(term in title_text for term in MINIJOB_TERMS):
        return "minijob"
    if any(term in title_text for term in PART_TIME_TERMS):
        return "part-time"
    return "other"


def _title_matches(title_text: str, category: Category) -> bool:
    return bool(category.keywords) and any(term in title_text for term in category.keywords)


def _effective_role(title: str, role_type: str, category: Category) -> str:
    """``any`` accepts ordinary (non-senior) roles, reported as ``regular``."""
    if role_type in category.levels:
        return role_type
    if "any" in category.levels and role_type in ("other", "regular"):
        if not any(term in _normalized(title) for term in SENIOR_TERMS):
            return "regular"
    return "other"


def match_category(title: str, role_type: str, profile: Profile = DEFAULT_PROFILE) -> tuple[str, str]:
    """Return ``(category_id, role_type)``; the first matching category wins."""
    title_text = f" {_normalized(title)} "
    for category in profile.categories:
        if category.keywords and not _title_matches(title_text, category):
            continue
        effective = _effective_role(title, role_type, category)
        if effective != "other":
            return category.id, effective
    return "other", role_type


def classify_category(
    title: str, role_type: str, description: str = "", profile: Profile = DEFAULT_PROFILE
) -> str:
    return match_category(title, role_type, profile)[0]


def categorize(job: Job, profile: Profile = DEFAULT_PROFILE) -> Job:
    """Fill in category, effective role type, score and reasons in place."""
    job.category, job.role_type = match_category(job.title, job.role_type, profile)
    job.score, job.reasons = score_job(job, profile)
    return job


def score_job(job: Job, profile: Profile = DEFAULT_PROFILE) -> tuple[int, list[str]]:
    title_text = f" {_normalized(job.title)} "
    description_text = f" {_normalized(job.description)} "
    text = f"{title_text} {description_text}"
    location = _normalized(job.location)
    role_type = job.role_type if job.role_type != "other" else classify_role(job.title, job.description)
    category = profile.category(job.category)
    score = 0
    reasons: list[str] = []

    if role_type == "werkstudent":
        score += 35
        reasons.append("Werkstudent role")
    elif role_type == "entry-level":
        score += 35
        reasons.append("Entry-level role")
    elif role_type in ("minijob", "part-time"):
        score += 45
        reasons.append("Part-time/minijob role")
    elif role_type == "regular":
        score += 25
        reasons.append("Matches your level")

    if category is not None and category.scope == "local" and not category.keywords:
        score += 15

    relevant = [category] if category is not None and category.keywords else list(profile.categories)
    matched = next((c for c in relevant if _title_matches(title_text, c)), None)
    if matched is not None:
        score += 40
        reasons.append(matched.reason())
    if any(term in text for term in ("student", "enrolled", "immatrikul", "studium", "university")):
        score += 8
        reasons.append("Student-friendly wording")
    cities = GERMAN_CITIES + ((profile.city.casefold(),) if profile.city else ())
    if any(term in location for term in cities):
        score += 7
        reasons.append("Located in Germany")
    if "english" in text or "englisch" in text:
        score += 3
        reasons.append("English mentioned")
    if any(term in _normalized(job.title) for term in SENIOR_TERMS):
        score -= 80
        reasons.append("Senior-level penalty")

    return max(0, min(100, score)), reasons


def plain_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()
