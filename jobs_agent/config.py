"""User configuration: what to search for, where, and how to rank it.

Everything personal lives in ``jobs-agent.toml`` at the repository root. When the
file is missing, ``DEFAULT_PROFILE`` is used: early-career technology and
technology-adjacent roles across Germany, ranked with the weighted model in
``core.py`` (see guides/ranking.md). It doubles as a worked example.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib

CONFIG_FILENAME = "jobs-agent.toml"

ROLE_LEVELS = ("werkstudent", "internship", "entry-level", "part-time", "minijob", "any")
SCOPES = ("germany", "local")
# "any" accepts every non-senior role; seniority is always rejected in core.py.
DEFAULT_LEVELS = ("any",)


@dataclass(frozen=True, slots=True)
class Family:
    """A group of roles inside a category, e.g. CORE_TECH or PRODUCT_PROJECT.

    ``points`` is the role-fit share of the 100-point score (max 20).
    ``title_hints`` lets a title with a weak hint ("Werkstudent Data") join this
    family when the description confirms it with one of ``keywords``.
    ``realism_bonus`` nudges families that are realistic entry points upwards.
    """

    id: str
    label: str
    keywords: tuple[str, ...]
    points: int = 20
    title_hints: tuple[str, ...] = ()
    realism_bonus: int = 0


@dataclass(frozen=True, slots=True)
class Category:
    """One tab on the dashboard and one group of searches."""

    id: str
    label: str
    queries: tuple[str, ...]
    scope: str = "germany"
    keywords: tuple[str, ...] = ()
    levels: tuple[str, ...] = DEFAULT_LEVELS
    families: tuple[Family, ...] = ()

    def role_families(self) -> tuple[Family, ...]:
        """Explicit families, or the category's own keywords as a single family.

        An empty result means "any title" (e.g. local part-time work).
        """
        if self.families:
            return self.families
        if self.keywords:
            return (Family(id=self.id, label=self.label, keywords=self.keywords),)
        return ()


@dataclass(frozen=True, slots=True)
class Profile:
    title: str = "Germany Job Agent"
    subtitle: str = ""
    city: str = ""
    radius_km: int = 35
    nearby_towns: tuple[str, ...] = ()
    min_score: int = 65
    notify_min_score: int = 75
    notify_limit: int = 5
    include_remote: bool = True
    gmail_client_id: str = ""
    categories: tuple[Category, ...] = field(default_factory=tuple)

    def category(self, category_id: str) -> Category | None:
        return next((c for c in self.categories if c.id == category_id), None)

    def category_label(self, category_id: str) -> str:
        category = self.category(category_id)
        if category is None:
            return category_id
        if category.scope == "local":
            return f"{category.label} · {self.city} area"
        return category.label

    def family_label(self, family_id: str) -> str:
        for category in self.categories:
            for family in category.role_families():
                if family.id == family_id:
                    return family.label
        category = self.category(family_id)
        return category.label if category else family_id

    def local_towns(self) -> frozenset[str]:
        return frozenset(t.casefold() for t in (self.city, *self.nearby_towns) if t)

    def public(self) -> dict:
        """Settings the static dashboard needs. Never put secrets in here."""
        return {
            "title": self.title,
            "subtitle": self.subtitle or self.default_subtitle(),
            "city": self.city,
            "gmail_client_id": self.gmail_client_id,
            "categories": [
                {
                    "id": c.id,
                    "label": self.category_label(c.id),
                    "scope": c.scope,
                    "families": [{"id": f.id, "label": f.label} for f in c.role_families()],
                }
                for c in self.categories
            ],
        }

    def default_subtitle(self) -> str:
        parts = []
        for c in self.categories:
            where = "across Germany" if c.scope == "germany" else f"around {self.city}"
            parts.append(f"{c.label} {where}")
        return "; ".join(parts) + "." if parts else ""


# --- The project author's own search (also the fallback example) -------------

CORE_TECH = "CORE_TECH"
PRODUCT_PROJECT = "PRODUCT_PROJECT"
BUSINESS_TECH = "BUSINESS_TECH"
ENTERPRISE_IT = "ENTERPRISE_IT"
BROADER_PROFESSIONAL = "BROADER_PROFESSIONAL"

DEFAULT_FAMILIES = (
    Family(
        id=CORE_TECH, label="Core Tech", points=20,
        keywords=(
            "software", "developer", "engineer", "backend", "frontend", "front end",
            "full stack", "fullstack", "data engineer", "data scientist", "data analyst",
            "machine learning", " ai ", "artificial intelligence", "cloud engineer",
            "devops", "platform engineer", "site reliability", " sre ", "cybersecurity",
            "cyber security", "security engineer", "qa engineer", "test automation",
            "quality assurance", "solutions engineer", "quant", "python", "java developer",
            "javascript", "typescript", "informatik", "computer science", "web development",
        ),
        # Title must carry one of these before description text may promote it
        # into CORE_TECH (see "title-first" in guides/ranking.md).
        title_hints=(
            " data ", " digital ", " tech ", " it ", " ki ", " cloud ", " cyber ",
            " system ", " systems ", " analytics ", " platform ",
        ),
    ),
    Family(
        id=PRODUCT_PROJECT, label="Product & Project", points=18, realism_bonus=2,
        keywords=(
            "product manager", "product management", "product analyst", "product operations",
            "project manager", "project management", "project coordinator", "projektmanage",
            "projektkoordinat", " pmo ", "digital transformation", "business transformation",
            "requirements engineer", "process analyst", "scrum master", "agile coach",
        ),
    ),
    Family(
        id=BUSINESS_TECH, label="Business & Tech", points=17, realism_bonus=2,
        keywords=(
            "business analyst", "technology analyst", "technical consultant",
            "technology consulting", "digital consultant", "it consultant",
            "junior consultant", "strategy consultant",
        ),
    ),
    Family(
        id=ENTERPRISE_IT, label="Enterprise IT", points=17, realism_bonus=2,
        keywords=(
            "service management", "itsm", "service delivery", "it operations",
            "technical operations", "application support", "application management",
            "application analyst", "application manager", "systems analyst",
            "system analyst", "business systems", "enterprise application",
            "implementation consultant", "implementation specialist",
            "integration specialist", "saas implementation", " erp ", " crm ",
            "cloud support", "infrastructure operations", "it governance",
            "change management", "release management", "incident management",
            "problem management", "it service",
        ),
    ),
    Family(
        id=BROADER_PROFESSIONAL, label="Broader Professional", points=14, realism_bonus=2,
        keywords=(
            "operations analyst", "business operations", "digital operations",
            "supply chain", "customer success", "rotational", "graduate programme",
            "graduate program", "trainee programme", "trainee program",
        ),
    ),
)

# Curated Bundesagentur für Arbeit searches covering every family. Each entry
# is one HTTP request per daily run, so the list stays hand-picked.
DEFAULT_QUERIES = (
    # CORE_TECH
    "werkstudent informatik", "werkstudent software", "werkstudent softwareentwicklung",
    "werkstudent data", "werkstudent machine learning", "werkstudent IT",
    "junior softwareentwickler", "junior developer", "graduate software engineer",
    "junior data analyst", "junior data engineer", "junior devops", "junior cybersecurity",
    # PRODUCT_PROJECT
    "werkstudent projektmanagement", "junior projektmanager", "product management intern",
    "junior product manager", "projektkoordinator IT", "PMO werkstudent",
    # BUSINESS_TECH
    "werkstudent business analyst", "junior business analyst", "IT consultant berufseinsteiger",
    # ENTERPRISE_IT
    "werkstudent IT service management", "junior application manager",
    "application support junior", "junior system analyst", "implementation consultant junior",
)

DEFAULT_PROFILE = Profile(
    title="Germany CS Jobs",
    subtitle=(
        "Live Werkstudent and entry-level technology roles, ranked for "
        "computer-science students in Germany."
    ),
    city="",
    radius_km=35,
    min_score=65,
    notify_min_score=75,
    notify_limit=5,
    categories=(
        Category(
            id="tech",
            label="Tech & adjacent roles",
            scope="germany",
            levels=("any",),
            families=DEFAULT_FAMILIES,
            queries=DEFAULT_QUERIES,
        ),
    ),
)


# --- Parsing ------------------------------------------------------------------

class ConfigError(ValueError):
    pass


def _strings(value: object, name: str, keep_spacing: bool = False) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{name} must be a list of strings")
    # Keywords keep their padding: " ai " must not become "ai", which matches "maintenance".
    return tuple((v if keep_spacing else v.strip()) for v in value if v.strip())


def _keywords(value: object, name: str) -> tuple[str, ...]:
    return tuple(k.casefold() for k in _strings(value, name, keep_spacing=True))


def _int(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ConfigError(f"{name} must be a whole number from {low} to {high}")
    return value


def _parse_families(raw_families: object, where: str) -> tuple[Family, ...]:
    if raw_families is None:
        return ()
    if not isinstance(raw_families, list):
        raise ConfigError(f"{where}.families must be a list of tables")
    families = []
    for index, raw in enumerate(raw_families, 1):
        name = f"{where}.families #{index}"
        if not isinstance(raw, dict):
            raise ConfigError(f"{name} must be a table")
        family_id = str(raw.get("id", "")).strip()
        keywords = _keywords(raw.get("keywords"), f"{name}.keywords")
        if not family_id or not keywords:
            raise ConfigError(f"{name}: id and at least one keyword are required")
        families.append(Family(
            id=family_id,
            label=str(raw.get("label", family_id)),
            keywords=keywords,
            points=_int(raw.get("points", 20), f"{name}.points", 0, 20),
            title_hints=_keywords(raw.get("title_hints"), f"{name}.title_hints"),
            realism_bonus=_int(raw.get("realism_bonus", 0), f"{name}.realism_bonus", 0, 5),
        ))
    return tuple(families)


def parse_config(data: dict) -> Profile:
    raw_profile = data.get("profile", {})
    if not isinstance(raw_profile, dict):
        raise ConfigError("[profile] must be a table")
    raw_categories = data.get("categories", [])
    if not isinstance(raw_categories, list) or not raw_categories:
        raise ConfigError("at least one [[categories]] entry is required")

    categories = []
    seen = set()
    for index, raw in enumerate(raw_categories, 1):
        where = f"categories #{index}"
        category_id = str(raw.get("id", "")).strip()
        if not category_id or category_id in seen:
            raise ConfigError(f"{where}: id must be present and unique")
        seen.add(category_id)
        scope = str(raw.get("scope", "germany"))
        if scope not in SCOPES:
            raise ConfigError(f"{where}: scope must be one of {', '.join(SCOPES)}")
        levels = _strings(raw.get("levels"), f"{where}.levels") or DEFAULT_LEVELS
        unknown = set(levels) - set(ROLE_LEVELS)
        if unknown:
            raise ConfigError(f"{where}: unknown levels {sorted(unknown)}")
        queries = _strings(raw.get("queries"), f"{where}.queries")
        if not queries:
            raise ConfigError(f"{where}: at least one search query is required")
        categories.append(Category(
            id=category_id,
            label=str(raw.get("label", category_id)),
            queries=queries,
            scope=scope,
            keywords=_keywords(raw.get("keywords"), f"{where}.keywords"),
            levels=levels,
            families=_parse_families(raw.get("families"), where),
        ))

    defaults = Profile()
    city = str(raw_profile.get("city", defaults.city)).strip()
    if not city and any(c.scope == "local" for c in categories):
        raise ConfigError('[profile] city is required when a category has scope = "local"')
    return Profile(
        title=str(raw_profile.get("title", defaults.title)),
        subtitle=str(raw_profile.get("subtitle", "")),
        city=city,
        radius_km=_int(raw_profile.get("radius_km", defaults.radius_km), "radius_km", 0, 200),
        nearby_towns=tuple(t.casefold() for t in _strings(raw_profile.get("nearby_towns"), "nearby_towns")),
        min_score=_int(raw_profile.get("min_score", defaults.min_score), "min_score", 0, 100),
        notify_min_score=_int(
            raw_profile.get("notify_min_score", defaults.notify_min_score), "notify_min_score", 0, 100
        ),
        notify_limit=_int(raw_profile.get("notify_limit", defaults.notify_limit), "notify_limit", 1, 50),
        include_remote=bool(raw_profile.get("include_remote", True)),
        gmail_client_id=str(raw_profile.get("gmail_client_id", "")).strip(),
        categories=tuple(categories),
    )


def load_config(path: str | Path | None = None) -> Profile:
    """Load ``path`` (or ./jobs-agent.toml); fall back to DEFAULT_PROFILE if absent."""
    config_path = Path(path) if path else Path.cwd() / CONFIG_FILENAME
    if not config_path.exists():
        if path:
            raise ConfigError(f"config file not found: {config_path}")
        return DEFAULT_PROFILE
    with config_path.open("rb") as handle:
        return parse_config(tomllib.load(handle))
