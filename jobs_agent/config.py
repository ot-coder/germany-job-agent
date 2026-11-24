"""User configuration: what to search for and where.

Everything personal lives in ``jobs-agent.toml`` at the repository root. When the
file is missing, ``DEFAULT_PROFILE`` is used (CS roles across Germany plus
part-time work around Leipzig), which doubles as a worked example.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib

CONFIG_FILENAME = "jobs-agent.toml"

ROLE_LEVELS = ("werkstudent", "entry-level", "part-time", "minijob", "any")
SCOPES = ("germany", "local")
DEFAULT_LEVELS = ("werkstudent", "entry-level", "part-time", "minijob")

DEFAULT_TECH_KEYWORDS = (
    "software", "developer", "engineer", "data", "python", "java", "javascript",
    "typescript", "cloud", "devops", "security", "cyber", "machine learning", " ai ",
    "frontend", "backend", "full stack", "fullstack", "qa", "test automation",
    "computer science", "informatik", "information technology", "product analyst",
    "business intelligence", "database", "systems administrator", "systemadministrator",
    "it support", "it-support", "web development",
)

DEFAULT_LEIPZIG_TOWNS = (
    "markkleeberg", "schkeuditz", "taucha", "markranstädt", "zwenkau", "böhlen",
    "rötha", "großpösna", "rackwitz", "borsdorf", "brandis", "machern", "naunhof",
    "krostitz", "delitzsch", "eilenburg", "borna", "grimma", "wurzen",
    "neukieritzsch", "pegau",
)


@dataclass(frozen=True, slots=True)
class Category:
    """One tab on the dashboard and one group of searches."""

    id: str
    label: str
    queries: tuple[str, ...]
    scope: str = "germany"
    keywords: tuple[str, ...] = ()
    levels: tuple[str, ...] = DEFAULT_LEVELS
    relevance_reason: str = ""

    def reason(self) -> str:
        return self.relevance_reason or f"{self.label} relevance"


@dataclass(frozen=True, slots=True)
class Profile:
    title: str = "Germany Student Jobs"
    subtitle: str = ""
    city: str = "Leipzig"
    radius_km: int = 35
    nearby_towns: tuple[str, ...] = ()
    min_score: int = 55
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
                {"id": c.id, "label": self.category_label(c.id), "scope": c.scope}
                for c in self.categories
            ],
        }

    def default_subtitle(self) -> str:
        parts = []
        for c in self.categories:
            where = "across Germany" if c.scope == "germany" else f"around {self.city}"
            parts.append(f"{c.label} {where}")
        return "; ".join(parts) + "." if parts else ""


DEFAULT_PROFILE = Profile(
    title="Germany Student Jobs",
    subtitle=(
        "Computer-science opportunities across Germany; part-time and minijob "
        "listings are restricted to Leipzig and nearby towns."
    ),
    city="Leipzig",
    radius_km=35,
    nearby_towns=DEFAULT_LEIPZIG_TOWNS,
    categories=(
        Category(
            id="cs",
            label="CS & Tech",
            scope="germany",
            keywords=DEFAULT_TECH_KEYWORDS,
            queries=(
                "werkstudent informatik",
                "werkstudent software",
                "junior softwareentwickler",
                "berufseinsteiger informatik",
            ),
            relevance_reason="Computer-science relevance",
        ),
        Category(
            id="part-time",
            label="Part-time & Minijob",
            scope="local",
            keywords=(),
            levels=("werkstudent", "part-time", "minijob"),
            queries=(
                "minijob",
                "teilzeit",
                "studentenjob",
                "aushilfe lager",
                "aushilfe gastronomie",
                "aushilfe restaurant",
            ),
        ),
    ),
)


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
            keywords=tuple(k.lower() for k in _strings(raw.get("keywords"), f"{where}.keywords", keep_spacing=True)),
            levels=levels,
            relevance_reason=str(raw.get("relevance_reason", "")),
        ))

    defaults = Profile()
    return Profile(
        title=str(raw_profile.get("title", defaults.title)),
        subtitle=str(raw_profile.get("subtitle", "")),
        city=str(raw_profile.get("city", defaults.city)).strip(),
        radius_km=int(raw_profile.get("radius_km", defaults.radius_km)),
        nearby_towns=tuple(t.lower() for t in _strings(raw_profile.get("nearby_towns"), "nearby_towns")),
        min_score=int(raw_profile.get("min_score", defaults.min_score)),
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

