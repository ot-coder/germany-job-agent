"""Classification and the weighted 0-100 ranking model.

See guides/ranking.md for why the rules and weights are what they
are. The role families and search terms themselves are configuration
(``jobs-agent.toml``; defaults in ``config.py``), so other fields can reuse the
same model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re

from .config import (
    BROADER_PROFESSIONAL,
    BUSINESS_TECH,
    CORE_TECH,
    DEFAULT_FAMILIES,
    DEFAULT_PROFILE,
    ENTERPRISE_IT,
    PRODUCT_PROJECT,
    Category,
    Family,
    Profile,
)

IRRELEVANT = "IRRELEVANT"

# Kept for callers and tests that use the default families directly.
FAMILY_TERMS: dict[str, tuple[str, ...]] = {f.id: f.keywords for f in DEFAULT_FAMILIES}
FAMILY_ORDER = tuple(f.id for f in DEFAULT_FAMILIES)
CORE_TECH_TITLE_HINTS = DEFAULT_FAMILIES[0].title_hints

__all__ = [
    "BROADER_PROFESSIONAL", "BUSINESS_TECH", "CORE_TECH", "ENTERPRISE_IT", "IRRELEVANT",
    "PRODUCT_PROJECT", "Job", "classify_role", "classify_level", "match_role",
    "score_job", "stable_job_id", "plain_text",
]

# Title-scoped hard rejection. "Manager" alone is deliberately absent here —
# only unambiguous seniority markers disqualify a role.
_SENIOR_TITLE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bprincipal\b", r"\bstaff\b",
        r"\bhead of\b", r"\bdirector\b", r"\bvp\b", r"\bvice president\b", r"\bchief\b",
        r"extensive leadership experience",
    )
)
_YEARS_PATTERN = re.compile(r"(\d+)\+\s*years?")

JUNIOR_TERMS = (
    "intern", "internship", "praktikum", "working student", "werkstudent",
    "student assistant", "studentische hilfskraft", "graduate", "trainee",
    "entry level", "entry-level", "berufseinsteiger", "new grad", "junior",
    "associate", "0-1 year", "0-2 year", "0 to 2 year",
)
_MODERATE_EXPERIENCE_PATTERN = re.compile(r"\b1\s*[-–to]{1,4}\s*2\s*years?\b|\b2\s*years?\s*(preferred|desired|plus)\b")
_STRONG_NEGATIVE_TERMS = ("senior leadership", "extensive leadership experience", "people management")

# Role levels, used for a category's ``levels`` filter and the dashboard's
# "role type" filter. Checked against the title only, in this order.
_LEVEL_TERMS = (
    ("werkstudent", ("werkstudent", "working student", "student assistant", "studentische hilfskraft")),
    ("internship", ("internship", "intern ", "intern)", "praktikum", "praktikant")),
    ("entry-level", ("junior", "entry level", "entry-level", "graduate", "trainee", "berufseinsteiger", "new grad")),
    ("minijob", ("minijob", "mini-job", "geringfügig", "556 euro", "520 euro")),
    ("part-time", ("teilzeit", "part time", "part-time", "aushilfe", "nebenjob", "studentenjob", "student job", "temporary staff")),
)

GERMANY_LOCATION_TERMS = (
    "germany", "deutschland", "berlin", "munich", "münchen", "munchen", "frankfurt",
    "hamburg", "cologne", "köln", "koln", "düsseldorf", "duesseldorf", "stuttgart",
    "leipzig", "dresden", "nuremberg", "nürnberg", "nurnberg", "hannover", "hanover",
    "bremen", "dortmund", "essen", "duisburg", "bochum", "wuppertal", "bielefeld",
    "bonn", "münster", "munster", "karlsruhe", "mannheim", "augsburg", "wiesbaden",
    "mönchengladbach", "gelsenkirchen", "braunschweig", "kiel", "chemnitz", "aachen",
    "halle", "magdeburg", "freiburg", "krefeld", "lübeck", "luebeck", "erfurt",
    "rostock", "kassel", "potsdam", "saarbrücken", "saarbruecken", "mainz",
    "regensburg", "ingolstadt", "würzburg", "wurzburg", "ulm", "heidelberg", "jena",
    "darmstadt", "göttingen", "goettingen",
)
EU_HUB_TERMS = (
    "amsterdam", "luxembourg", "dublin", "warsaw", "prague", "stockholm", "london",
    "zurich", "paris", "netherlands", "ireland", "poland", "czech", "sweden",
    "united kingdom", "switzerland", "france",
)

_STRICT_GERMAN_TERMS = (
    "muttersprachlich", "native german", "verhandlungssicheres deutsch",
    "german c1", "german c2", "c1 deutsch", "c2 deutsch", "deutsch c1", "deutsch c2",
    "fließend deutsch zwingend",
)
_MODERATE_GERMAN_TERMS = ("fluent german", "deutsch fließend", "verhandlungssicher")
_OPEN_GERMAN_TERMS = (
    "german b1", "german b2", "deutsch b1", "deutsch b2", "gute deutschkenntnisse",
    "deutschkenntnisse von vorteil", "conversational german", "basic german",
)

_CAREER_VALUE_TERMS = (
    "enterprise", "stakeholder", "cross-functional", "cross functional",
    "implementation", "platform", "cloud", "agile", "scrum", "roadmap", " api ",
    " crm ", " erp ", "saas", "data-driven", "automation", "integration",
)

# Small, intentionally short known-employer map. Anything not listed defaults
# to "Core" rather than inventing false precision. See guides/ranking.md.
KNOWN_EMPLOYERS: dict[str, str] = {
    "google": "Reach", "amazon": "Reach", "microsoft": "Reach", "meta": "Reach",
    "apple": "Reach", "netflix": "Reach", "mckinsey": "Reach", "bcg": "Reach",
    "boston consulting group": "Reach", "goldman sachs": "Reach", "sap": "Reach",
    "siemens": "Reach", "deutsche bank": "Reach", "bmw": "Reach",
    "mercedes-benz": "Reach", "mercedes benz": "Reach", "porsche": "Reach",
    "bosch": "Core", "allianz": "Core", "deutsche bahn": "Core", "telekom": "Core",
    "volkswagen": "Core", "zalando": "Core", "delivery hero": "Accessible",
    "n26": "Accessible", "trade republic": "Accessible", "personio": "Accessible",
    "check24": "Accessible", "celonis": "Accessible", "flixbus": "Accessible",
    "spryker": "Accessible",
}


@dataclass(slots=True)
class Job:
    id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    source: str
    category: str = ""
    role_family: str = ""
    role_type: str = "regular"
    seniority: str = "neutral"
    employer_category: str = "Core"
    language_requirement: str = "open"
    remote: bool = False
    published_at: str = ""
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    first_seen_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True, slots=True)
class RoleMatch:
    category: Category | None
    family: Family | None
    role_type: str
    seniority: str

    @property
    def family_id(self) -> str:
        if self.category is None:
            return IRRELEVANT
        return self.family.id if self.family else self.category.id


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def stable_job_id(company: str, title: str, location: str) -> str:
    key = "|".join(_normalized(v) for v in (company, title, location))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def _is_senior_title(title_text: str) -> bool:
    if any(pattern.search(title_text) for pattern in _SENIOR_TITLE_PATTERNS):
        return True
    return any(int(match) >= 3 for match in _YEARS_PATTERN.findall(title_text))


def classify_level(title: str) -> str:
    """werkstudent / internship / entry-level / minijob / part-time / regular / senior."""
    title_text = f" {_normalized(title)} "
    if _is_senior_title(title_text):
        return "senior"
    for level, terms in _LEVEL_TERMS:
        if any(term in title_text for term in terms):
            return level
    return "regular"


def _level_allowed(category: Category, role_type: str) -> bool:
    return "any" in category.levels or role_type in category.levels


def _match_family(families: tuple[Family, ...], title_text: str, combined: str) -> Family | None:
    for family in families:
        if any(term in title_text for term in family.keywords):
            return family
    # Description fallback, used ONLY when the title carries its own weak hint.
    # Matching family keywords against descriptions alone produced false
    # positives (a Sales Account Executive at an "AI-native" company became
    # CORE_TECH), so the title has to point that way first.
    for family in families:
        if family.title_hints and any(hint in title_text for hint in family.title_hints):
            if any(term in combined for term in family.keywords):
                return family
    return None


def match_role(title: str, description: str = "", profile: Profile = DEFAULT_PROFILE) -> RoleMatch:
    """Find the first category (and family within it) that this role belongs to."""
    title_text = f" {_normalized(title)} "
    if _is_senior_title(title_text):
        return RoleMatch(None, None, "senior", "senior")
    combined = f"{title_text}{_normalized(description)} "
    seniority = "junior" if any(term in combined for term in JUNIOR_TERMS) else "neutral"
    role_type = classify_level(title)
    for category in profile.categories:
        if not _level_allowed(category, role_type):
            continue
        families = category.role_families()
        if not families:
            return RoleMatch(category, None, role_type, seniority)
        family = _match_family(families, title_text, combined)
        if family is not None:
            return RoleMatch(category, family, role_type, seniority)
    return RoleMatch(None, None, role_type, seniority)


def classify_role(title: str, description: str = "", profile: Profile = DEFAULT_PROFILE) -> tuple[str, str]:
    """Returns (role_family, seniority). seniority is 'senior', 'junior', or 'neutral'."""
    match = match_role(title, description, profile)
    return match.family_id, match.seniority


def classify_employer(company: str) -> str:
    name = f" {_normalized(company)} "
    for known, category in KNOWN_EMPLOYERS.items():
        if f" {known} " in name or name.strip() == known:
            return category
    return "Core"


def _years_required(text: str) -> int:
    matches = _YEARS_PATTERN.findall(text)
    return max((int(value) for value in matches), default=0)


def _eligibility_score(text: str) -> tuple[int, str]:
    if _years_required(text) >= 3 or any(term in text for term in _STRONG_NEGATIVE_TERMS):
        return 4, "Experience requirement likely above entry level"
    if any(term in text for term in JUNIOR_TERMS):
        return 20, "Clear entry-level/student framing"
    if _MODERATE_EXPERIENCE_PATTERN.search(text):
        return 13, "Light experience expectation (1-2 years)"
    return 9, "Experience level not clearly stated"


def _realism_score(realism_bonus: int, employer_category: str, seniority: str) -> tuple[int, str]:
    base = 10
    if employer_category == "Reach":
        reason = "Highly selective employer — realistic odds are lower"
        base -= 4
    elif employer_category == "Accessible":
        reason = "Accessible employer — realistic odds are healthier"
        base += 3
    else:
        reason = "Moderate competitiveness expected"
    base += realism_bonus
    if seniority == "junior":
        base += 2
    return max(0, min(15, base)), reason


def _location_score(location_text: str, remote: bool, profile: Profile) -> tuple[int, str]:
    home = (profile.city.casefold(),) if profile.city else ()
    if any(term in location_text for term in GERMANY_LOCATION_TERMS + home):
        return 10, "Located in Germany"
    if remote or "remote" in location_text:
        return 6, "Remote role — Germany eligibility unclear"
    if any(term in location_text for term in EU_HUB_TERMS):
        return 5, "Other European hub — work authorization unverified"
    return 2, "Location outside primary target markets"


def _language_score(text: str) -> tuple[int, str, str]:
    if any(term in text for term in _STRICT_GERMAN_TERMS):
        return 1, "Native/C1+ German required", "strict"
    if any(term in text for term in _MODERATE_GERMAN_TERMS):
        return 5, "Fluent German requested — mandatoriness unclear", "moderate"
    if any(term in text for term in _OPEN_GERMAN_TERMS):
        return 8, "German B1/B2 friendly wording", "open"
    if "german" not in text and "deutsch" not in text:
        return 10, "English-only role", "open"
    return 9, "No strict German requirement detected", "open"


def _skills_score(family: Family | None, text: str) -> tuple[int, str, str]:
    if family is None:  # "any title" category, e.g. local part-time work
        return 6, "Matches your local search", "some"
    hits = sum(1 for term in family.keywords if term in text)
    if hits >= 2:
        return 10, "Strong keyword relevance to role family", "strong"
    if hits == 1:
        return 6, "Some keyword relevance", "some"
    return 2, "Limited keyword overlap", "low"


def _career_value_score(text: str) -> tuple[int, str, str]:
    hits = sum(1 for term in _CAREER_VALUE_TERMS if term in text)
    points = min(10, 4 + hits * 2)
    if hits >= 2:
        return points, "Builds transferable enterprise/technical experience", "high"
    return points, "Standard progression value", "base"


def _parse_published(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _recency_score(published_at: str) -> tuple[int, str]:
    parsed = _parse_published(published_at)
    if parsed is None:
        return 3, "Publish date unknown"
    age_days = (datetime.now(timezone.utc) - parsed).days
    if age_days <= 14:
        return 5, "Recently posted"
    if age_days <= 30:
        return 3, "Posted within the last month"
    return 1, "Posted over a month ago"


def score_job(job: Job, profile: Profile = DEFAULT_PROFILE) -> tuple[int, list[str]]:
    """Scores a job 0-100 and returns (score, reasons).

    Also fills in job.category, job.role_family, job.role_type, job.seniority,
    job.employer_category and job.language_requirement as a side effect,
    matching the normalizers' ``job.score, job.reasons = score_job(job)`` pattern.
    """
    match = match_role(job.title, job.description, profile)
    job.category = match.category.id if match.category else "other"
    job.role_family = match.family_id
    job.role_type = match.role_type
    job.seniority = match.seniority
    job.employer_category = classify_employer(job.company)
    if match.category is None:
        if match.seniority == "senior":
            return 0, ["Senior-level or out-of-scope role"]
        return 0, ["Outside your configured search"]

    title_text = f" {_normalized(job.title)} "
    text = f"{title_text} {_normalized(job.description)} "
    location_text = f" {_normalized(job.location)} "
    family = match.family

    role_fit_points = family.points if family else 20
    role_fit_reason = f"Credible {family.label if family else match.category.label} entry point"
    eligibility_points, eligibility_reason = _eligibility_score(text)
    realism_points, realism_reason = _realism_score(
        family.realism_bonus if family else 0, job.employer_category, match.seniority
    )
    location_points, location_reason = _location_score(location_text, job.remote, profile)
    language_points, language_reason, language_label = _language_score(text)
    job.language_requirement = language_label
    skills_points, skills_reason, skills_label = _skills_score(family, text)
    career_points, career_reason, career_label = _career_value_score(text)
    recency_points, recency_reason = _recency_score(job.published_at)

    score = (
        role_fit_points + eligibility_points + realism_points + location_points
        + language_points + skills_points + career_points + recency_points
    )

    reasons = [role_fit_reason, eligibility_reason, location_reason, language_reason]
    if skills_label == "strong":
        reasons.append(skills_reason)
    elif career_label == "high":
        reasons.append(career_reason)
    elif realism_reason.startswith("Highly selective"):
        reasons.append(realism_reason)
    elif recency_reason == "Recently posted":
        reasons.append(recency_reason)

    return max(0, min(100, score)), reasons[:5]


def plain_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()
