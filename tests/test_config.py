import tempfile
import tomllib
import unittest
from pathlib import Path

from jobs_agent.config import DEFAULT_PROFILE, ConfigError, load_config, parse_config
from jobs_agent.core import Job, classify_category, score_job
from jobs_agent.setup import build_config, split_terms
from jobs_agent.sources import fetch_all


def ba_job(title, town, ref):
    return {"stellenangebotsTitel": title, "firma": f"{town} GmbH", "referenznummer": ref,
            "stellenlokationen": [{"adresse": {"ort": town, "land": "DEUTSCHLAND"}}]}


class ConfigTests(unittest.TestCase):
    def test_repository_config_reproduces_default_profile(self):
        self.assertEqual(load_config(Path(__file__).parent.parent / "jobs-agent.toml"), DEFAULT_PROFILE)

    def test_missing_default_file_falls_back_but_explicit_path_must_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ConfigError):
                load_config(Path(directory) / "nope.toml")

    def test_keyword_padding_is_preserved(self):
        profile = parse_config(tomllib.loads(
            '[[categories]]\nid="x"\nqueries=["q"]\nkeywords=[" ai "]\n'
        ))
        self.assertEqual(profile.categories[0].keywords, (" ai ",))
        self.assertEqual(classify_category("Werkstudent Maintenance", "werkstudent", profile=profile), "other")
        self.assertEqual(classify_category("Werkstudent AI Research", "werkstudent", profile=profile), "x")

    def test_rejects_unknown_levels_and_missing_queries(self):
        with self.assertRaises(ConfigError):
            parse_config({"categories": [{"id": "a", "queries": ["q"], "levels": ["boss"]}]})
        with self.assertRaises(ConfigError):
            parse_config({"categories": [{"id": "a"}]})

    def test_public_config_has_no_secrets_and_labels_local_tabs(self):
        public = DEFAULT_PROFILE.public()
        self.assertEqual(set(public), {"title", "subtitle", "city", "gmail_client_id", "categories"})
        self.assertEqual(public["categories"][1]["label"], "Part-time & Minijob · Leipzig area")


class SetupTests(unittest.TestCase):
    def test_split_terms_dedupes_and_limits(self):
        self.assertEqual(split_terms(" Pflege,pflege ; Krankenpflege ,, a"), ["pflege", "krankenpflege"])
        self.assertEqual(len(split_terms(",".join(f"t{i}" for i in range(20)))), 6)

    def test_generated_config_is_valid_and_drives_classification(self):
        text = build_config("pflege, krankenpflege", "Dresden", radius_km=25, level="any", scope="local")
        profile = parse_config(tomllib.loads(text))
        self.assertEqual(profile.city, "Dresden")
        field = profile.category("field")
        self.assertEqual(field.scope, "local")
        self.assertIn("pflege", field.queries)
        self.assertEqual(classify_category("Pflegefachkraft (m/w/d)", "other", profile=profile), "field")
        self.assertEqual(classify_category("Senior Pflegedienstleitung", "other", profile=profile), "other")
        self.assertIsNotNone(profile.category("part-time"))

    def test_setup_escapes_user_text(self):
        text = build_config('data", evil = "1', 'Köln"\n[x]')
        profile = parse_config(tomllib.loads(text))
        self.assertEqual(profile.city, 'Köln" [x]')

    def test_setup_validates_input(self):
        for kwargs in ({"field": " , ", "city": "Leipzig"}, {"field": "data", "city": " "},
                       {"field": "data", "city": "Leipzig", "radius_km": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build_config(**kwargs)


class GenericProfileFetchTests(unittest.TestCase):
    def setUp(self):
        self.profile = parse_config(tomllib.loads(
            build_config("pflege", "Dresden", radius_km=20, level="any", scope="local", local_part_time=False)
        ))

    def test_local_field_trusts_bundesagentur_radius_without_town_list(self):
        requested = []

        def fake_fetch(url):
            requested.append(url)
            if "arbeitnow" in url:
                return {"data": [{"title": "Pflegefachkraft", "company_name": "Far", "location": "Hamburg",
                                  "url": "https://x/far", "description": ""}]}
            if "remotive" in url:
                return {"jobs": []}
            return {"stellenangebote": [ba_job("Pflegefachkraft (m/w/d)", "Radebeul", "R-1")]}

        jobs = fetch_all(fetch_json=fake_fetch, profile=self.profile)
        self.assertEqual([j.location for j in jobs], ["Radebeul, Deutschland"])
        self.assertEqual(jobs[0].role_type, "regular")
        ba_urls = [u for u in requested if "arbeitsagentur" in u]
        self.assertTrue(ba_urls and all("wo=Dresden&umkreis=20" in u for u in ba_urls))

    def test_regular_role_scores_above_threshold_with_field_match(self):
        job = Job(id="1", title="Pflegefachkraft", company="A", location="Dresden", url="", description="",
                  source="t", role_type="regular", category="field")
        score, reasons = score_job(job, self.profile)
        self.assertGreaterEqual(score, self.profile.min_score)
        self.assertIn("Pflege relevance", reasons)


if __name__ == "__main__":
    unittest.main()
