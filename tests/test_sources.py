import unittest

from dataclasses import replace

from jobs_agent.config import DEFAULT_PROFILE, Category
from jobs_agent.core import CORE_TECH
from jobs_agent.setup import PART_TIME_LEVELS, PART_TIME_QUERIES
from jobs_agent.sources import (
    BA_QUERIES,
    _parse_ba_search_html,
    fetch_all,
    is_local,
    normalize_arbeitnow,
    normalize_ba,
)

LEIPZIG_TOWNS = ("markkleeberg", "schkeuditz", "taucha", "delitzsch", "borna", "großpösna")

# The default (author's) profile plus a local part-time tab, as the setup form writes it.
WITH_PART_TIME = replace(
    DEFAULT_PROFILE,
    city="Leipzig",
    categories=DEFAULT_PROFILE.categories + (Category(
        id="part-time", label="Part-time & Minijob", scope="local",
        levels=tuple(PART_TIME_LEVELS), queries=tuple(PART_TIME_QUERIES),
    ),),
)
WITH_TOWNS = replace(WITH_PART_TIME, nearby_towns=LEIPZIG_TOWNS)


class SourceTests(unittest.TestCase):
    def test_normalizes_arbeitnow_job(self):
        raw = {
            "slug": "working-student-python-acme",
            "title": "Working Student Python Developer",
            "company_name": "Acme",
            "location": "Berlin",
            "url": "https://example.com/job",
            "description": "<p>For enrolled computer science students</p>",
            "remote": False,
            "created_at": 1700000000,
        }
        job = normalize_arbeitnow(raw)
        self.assertEqual(job.role_family, CORE_TECH)
        self.assertEqual(job.description, "For enrolled computer science students")
        self.assertEqual(job.source, "arbeitnow")
        self.assertGreaterEqual(job.score, 65)

    def test_normalizes_bundesagentur_job(self):
        raw = {
            "titel": "Werkstudent Informatik (m/w/d)", "arbeitgeber": "PC Shop",
            "refnr": "10001-ABC-S", "arbeitsort": {"ort": "Stralsund", "region": "Mecklenburg-Vorpommern", "land": "Deutschland"},
            "beruf": "Informatiker/in", "aktuelleVeroeffentlichungsdatum": "2026-03-17",
        }
        job = normalize_ba(raw)
        self.assertEqual(job.source, "bundesagentur")
        self.assertEqual(job.location, "Stralsund, Mecklenburg-Vorpommern, Deutschland")
        self.assertIn("10001-ABC-S", job.url)
        self.assertGreaterEqual(job.score, 65)

    def test_normalizes_current_bundesagentur_ssr_job(self):
        raw = {
            "stellenangebotsTitel": "Werkstudent Softwareentwicklung (m/w/d)",
            "firma": "Example GmbH",
            "referenznummer": "10000-SSR-S",
            "stellenlokationen": [{"adresse": {
                "ort": "Berlin", "region": "BERLIN", "land": "DEUTSCHLAND"
            }}],
            "hauptberuf": "Softwareentwickler/in",
            "datumErsteVeroeffentlichung": "2026-08-04",
        }
        job = normalize_ba(raw)
        self.assertEqual(job.company, "Example GmbH")
        self.assertEqual(job.location, "Berlin, Berlin, Deutschland")
        self.assertIn("10000-SSR-S", job.url)
        self.assertGreaterEqual(job.score, 70)

    def test_fetch_all_keeps_only_suitable_roles_and_deduplicates(self):
        def fake_fetch(url):
            if "arbeitnow" in url:
                return {"data": [
                    {"title": "Werkstudent Software Engineer", "company_name": "Acme", "location": "Berlin", "url": "https://a/1", "description": "Computer science student Python"},
                    {"title": "Senior Software Engineer", "company_name": "Acme", "location": "Berlin", "url": "https://a/2", "description": "Python"},
                ]}
            if "arbeitsagentur" in url:
                return {"stellenangebote": [
                    {"titel": "Werkstudent Informatik", "arbeitgeber": "Gamma", "refnr": "BA-1", "arbeitsort": {"ort": "Hamburg", "land": "Deutschland"}, "beruf": "Informatiker/in"}
                ]}
            return {"jobs": [
                {"title": "Werkstudent Software Engineer", "company_name": "Acme", "candidate_required_location": "Berlin", "url": "https://r/1", "description": "Computer science student Python"},
                {"title": "Junior Data Analyst", "company_name": "Beta", "candidate_required_location": "Germany", "url": "https://r/2", "description": "Entry level data role"},
            ]}

        result = fetch_all(fetch_json=fake_fetch, min_score=60)
        self.assertEqual({job.title for job in result.jobs}, {"Werkstudent Software Engineer", "Werkstudent Informatik", "Junior Data Analyst"})

    def test_fetch_all_reports_evaluated_and_duplicate_stats(self):
        # "Werkstudent Software Engineer" / Acme / Berlin appears from both
        # arbeitnow and remotive with the same normalized id -> one duplicate.
        def fake_fetch(url):
            if "arbeitnow" in url:
                return {"data": [
                    {"title": "Werkstudent Software Engineer", "company_name": "Acme", "location": "Berlin", "url": "https://a/1", "description": "Computer science student Python"},
                ]}
            if "arbeitsagentur" in url:
                return {"stellenangebote": []}
            return {"jobs": [
                {"title": "Werkstudent Software Engineer", "company_name": "Acme", "candidate_required_location": "Berlin", "url": "https://r/1", "description": "Computer science student Python"},
            ]}

        result = fetch_all(fetch_json=fake_fetch, min_score=60)
        self.assertEqual(result.evaluated, 2)
        self.assertEqual(result.duplicates_removed, 1)
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.passed_threshold, 1)

    def test_fetch_all_dedup_keeps_best_scoring_variant(self):
        # Two sources report the same job at the same normalized id, but the
        # remotive copy has a stronger, more complete description that scores
        # higher (extra career-value signal). The higher-scoring variant must
        # be the one retained.
        def fake_fetch(url):
            if "arbeitnow" in url:
                return {"data": [
                    {"title": "Werkstudent Data", "company_name": "Acme", "location": "Berlin, Germany", "url": "https://a/1", "description": "Python."},
                ]}
            if "arbeitsagentur" in url:
                return {"stellenangebote": []}
            return {"jobs": [
                {
                    "title": "Werkstudent Data", "company_name": "Acme",
                    "candidate_required_location": "Berlin, Germany", "url": "https://r/1",
                    "description": "Python, SQL, and cloud tooling for enrolled computer science students. English team.",
                },
            ]}

        result = fetch_all(fetch_json=fake_fetch, min_score=60)
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].url, "https://r/1")

    def test_fetch_all_continues_when_bundesagentur_is_unavailable(self):
        def fake_fetch(url):
            if "arbeitnow" in url:
                return {"data": [{
                    "title": "Werkstudent Python Developer",
                    "company_name": "Acme",
                    "location": "Berlin",
                    "url": "https://example.test/job",
                    "description": "Computer science student Python",
                }]}
            if "remotive" in url:
                return {"jobs": []}
            raise OSError("404 Not Found")

        result = fetch_all(fetch_json=fake_fetch, min_score=60)
        self.assertEqual([job.title for job in result.jobs], ["Werkstudent Python Developer"])

    def test_fetch_all_fails_if_every_internet_source_is_unavailable(self):
        def failing_fetch(url):
            raise OSError("503 Unavailable")

        with self.assertRaisesRegex(RuntimeError, "All job sources failed"):
            fetch_all(fetch_json=failing_fetch)


    def test_default_profile_searches_curated_queries_nationwide(self):
        requested = []

        def fake_fetch(url):
            requested.append(url)
            return {"data": [], "jobs": [], "stellenangebote": []}

        fetch_all(fetch_json=fake_fetch)
        ba = [url for url in requested if "arbeitsagentur" in url]
        self.assertEqual(len(ba), len(BA_QUERIES))
        self.assertTrue(all("wo=Deutschland" in url for url in ba))

    def test_parses_bundesagentur_ssr_search_state(self):
        html = '''<html><script id="ng-state" type="application/json">{
          "suchergebnis": {"ergebnisliste": [{"referenznummer": "SSR-1"}]}
        }</script></html>'''
        self.assertEqual(
            _parse_ba_search_html(html),
            {"stellenangebote": [{"referenznummer": "SSR-1"}]},
        )


class LocalCategoryTests(unittest.TestCase):
    def test_nearby_towns_accept_city_and_listed_towns_only(self):
        for location in (
            "Leipzig, Sachsen, Deutschland",
            "Markkleeberg, Sachsen, Deutschland",
            "Großpösna, Sachsen, Deutschland",
        ):
            with self.subTest(location=location):
                self.assertTrue(is_local(location, WITH_TOWNS))
        for location in ("Stuttgart, Baden-Württemberg, Deutschland", "Dresden, Sachsen, Deutschland", "Remote"):
            with self.subTest(location=location):
                self.assertFalse(is_local(location, WITH_TOWNS))

    def test_minijob_lands_in_local_part_time_category(self):
        raw = {
            "stellenangebotsTitel": "Minijob Lagerhelfer (m/w/d)", "firma": "Warehouse GmbH",
            "referenznummer": "GENERAL-1",
            "stellenlokationen": [{"adresse": {"ort": "Leipzig", "land": "DEUTSCHLAND"}}],
            "hauptberuf": "Helfer/in - Lagerwirtschaft",
        }
        job = normalize_ba(raw, WITH_PART_TIME)
        self.assertEqual(job.role_type, "minijob")
        self.assertEqual(job.category, "part-time")
        self.assertGreaterEqual(job.score, 65)

    def test_tech_titles_still_prefer_the_tech_category(self):
        job = normalize_ba({
            "titel": "Werkstudent Informatik", "arbeitgeber": "Gamma", "refnr": "BA-1",
            "arbeitsort": {"ort": "Leipzig", "land": "Deutschland"}, "beruf": "Informatiker/in",
        }, WITH_PART_TIME)
        self.assertEqual((job.category, job.role_family), ("tech", CORE_TECH))

    def test_part_time_jobs_kept_only_in_listed_towns(self):
        def fake_fetch(url):
            if "arbeitnow" in url:
                return {"data": [
                    {"title": "Minijob Lagerhelfer", "company_name": "L", "location": "Leipzig, Sachsen, Deutschland", "url": "https://e/1", "description": "Flexible minijob shifts"},
                    {"title": "Minijob Lagerhelfer", "company_name": "S", "location": "Stuttgart, Baden-Württemberg, Deutschland", "url": "https://e/2", "description": "Flexible minijob shifts"},
                    {"title": "Aushilfe Restaurant", "company_name": "M", "location": "Markkleeberg, Sachsen, Deutschland", "url": "https://e/3", "description": "Teilzeit"},
                ]}
            return {"jobs": [], "stellenangebote": []}

        result = fetch_all(fetch_json=fake_fetch, profile=WITH_TOWNS)
        self.assertEqual(
            {job.location for job in result.jobs},
            {"Leipzig, Sachsen, Deutschland", "Markkleeberg, Sachsen, Deutschland"},
        )

    def test_local_queries_use_city_radius_and_trust_it_without_town_list(self):
        requested = []

        def fake_fetch(url):
            requested.append(url)
            if "minijob" in url:
                return {"stellenangebote": [{
                    "stellenangebotsTitel": "Minijob Lagerhelfer", "firma": "Warehouse GmbH",
                    "referenznummer": "MINI-1",
                    "stellenlokationen": [{"adresse": {"ort": "Schkeuditz", "land": "DEUTSCHLAND"}}],
                    "hauptberuf": "Helfer/in - Lagerwirtschaft",
                }]}
            return {"data": [], "jobs": [], "stellenangebote": []}

        result = fetch_all(fetch_json=fake_fetch, profile=WITH_PART_TIME)
        self.assertEqual([job.category for job in result.jobs], ["part-time"])
        local = [url for url in requested if any(q.replace(" ", "+") in url for q in PART_TIME_QUERIES)]
        self.assertEqual(len(local), len(PART_TIME_QUERIES))
        self.assertTrue(all("wo=Leipzig" in url and "umkreis=35" in url for url in local))


if __name__ == "__main__":
    unittest.main()
