# How jobs are classified and ranked

This explains *why* the agent searches, classifies and ranks the way it does.
Read it before changing `jobs_agent/core.py`, `jobs_agent/sources.py` or
`jobs_agent/publish.py`. A change that looks like a bug fix in isolation can
quietly break the rules below, for example the "manager" rule, German-language
tolerance or the notification anti-spam cap.

The role families, their keywords and weights, the Bundesagentur queries and
the thresholds are configuration in [`jobs-agent.toml`](../jobs-agent.toml).
`jobs_agent/config.py` holds the defaults. The scoring components and the
seniority rules are code in `jobs_agent/core.py`.

## Goal of the default search

The default search finds **early-career** roles: internships, working-student
positions, graduate programmes and entry-level jobs. It deliberately covers
more than software engineering. Adjacent technology, product, project, IT-service,
implementation, support and business-technology roles are valid and sometimes
better entry points, so they are ranked alongside each other rather than
filtered out.

## Role families

Each category can split its field into families, checked against the job
title in order. The first match wins. The default search uses:

- **Core Tech:** software, backend/frontend/full-stack, data engineering, data
  science and analytics, AI/ML, cloud, DevOps, platform, cybersecurity, QA and
  test automation, solutions engineering.
- **Product & Project:** product and project management (including intern,
  associate and junior roles), product analyst and operations, project
  coordination, PMO, requirements engineering, digital transformation.
- **Business & Tech:** business analyst, technology analyst, technical and
  technology consulting.
- **Enterprise IT:** ITSM, service delivery, IT operations, application
  support/management/analysis, systems analysis, implementation and
  integration, ERP/CRM, change/release/incident/problem management.
- **Broader Professional:** operations, supply chain, customer success,
  rotational and graduate programmes.

Anything else, and any senior role, is **out of scope** and never published.

**Classification is title-first, by design.** Job titles are short and
specific. Descriptions are long and full of boilerplate. Matching family
keywords against descriptions produced real false positives: a *Sales Account
Executive* scored 92 as Core Tech because the employer's About-Us text called
itself "AI-native". So a job only joins a family through its description when
the *title* already carries a hint (`data`, `digital`, `tech`, `IT`, `cloud`,
`cyber`, `system(s)`, `analytics`, `platform`, `KI`) **and** the description
confirms it.

Known edge case, left as is: a title that contains "AI" as company branding
("…at AI Audit-Tech Startup") can still match directly.

## Seniority ("the manager rule")

**"Manager" alone never rejects a role.** Junior Project Manager, Product
Manager Intern, Application Manager and Junior IT Service Manager are all
legitimate entry points.

Titles are rejected only for unambiguous seniority: `senior`, `sr.`, `lead`,
`principal`, `staff`, `head of`, `director`, `vp`, `vice president`, `chief`,
`extensive leadership experience`, or an explicit `N+ years` with N ≥ 3. The
exact list is in `tests/test_core.py::ManagerRegressionTests`. Extend it rather
than working around it.

## The score

Deterministic, additive, out of 100. It is a **ranking heuristic**, not a
calibrated probability.

| Component | Points | What it captures |
|---|---|---|
| Role fit | 20 | How credible an entry point the role family is. Families are kept close (14–20) so a strong IT-service role isn't buried under a mediocre engineering one. |
| Experience level | 20 | Intern/Werkstudent/junior/graduate wording scores highest; "3+/5+ years" or senior-leadership requirements score lowest. |
| Realism | 15 | Employer selectivity (a short known-employer list: Reach / Core / Accessible, default Core) plus family and junior signals, so keyword-dense elite roles don't automatically top the list. |
| Location | 10 | Germany or remote-Germany highest; other European hubs lower, with a work-permit caveat; elsewhere low. |
| Language | 10 | English-only or B1/B2-friendly German highest; native/C1+ German required lowest. German is never an automatic rejection. |
| Keyword relevance | 10 | Overlap with the matched family's keywords. |
| Career value | 10 | Enterprise, stakeholder, implementation, platform, cloud, agile, API, CRM/ERP, SaaS signals: does the role build transferable experience? |
| Recency | 5 | Recently posted roles rank slightly higher. |

Jobs below `min_score` (65) are not published. Out-of-scope roles are never
published, whatever their score.

### Notification tiers

| Score | Tier |
|---|---|
| 90–100 | EXCEPTIONAL |
| 82–89 | APPLY |
| 75–81 | REVIEW |
| 65–74 | dashboard only |
| below 65 | not published |

## Anti-spam rules

The daily notification (GitHub issue, and Telegram if configured) lists at most
`notify_limit` (5) jobs: the highest-scoring *genuinely new* jobs at
`notify_min_score` (75) or above. The threshold is never lowered to fill the
list, and a day with nothing qualifying sends nothing.

Every passing job is still written to `docs/jobs.json`. Once a job's ID has
been published, it is never "new" again, so a job that missed the cap on day 1
is on the dashboard but doesn't resurface in notifications later. See
`tests/test_publish.py::test_jobs_omitted_by_telegram_cap_do_not_reappear_as_new_next_run`.

## Deduplication

`stable_job_id()` hashes the normalised company, title and location.
`fetch_all()` removes duplicates across all sources *before* the threshold,
keeping the higher-scoring copy, so a thin listing never beats a richer copy
of the same job.

## Sources and known gaps

Bundesagentur für Arbeit (curated queries per family), Arbeitnow and Remotive:
all unauthenticated public APIs, with no scraping framework or headless browser.

Likely under-covered:

- Campus and graduate programmes at large multinationals, which mostly live on
  their own applicant-tracking systems (Workday, SmartRecruiters, Greenhouse,
  SuccessFactors) and rarely reach these boards.
- Next year's graduate cohorts, which usually open 9–12 months ahead.
- English-language graduate schemes outside Germany.
- Enterprise-IT and business-technology roles at large corporates and
  consultancies, which more often post only on their own career sites.

Monitoring employer career pages directly is a possible future addition. If it
is added, it should be one more small source adapter, not a scraping framework.
