import json
import tempfile
import unittest
from pathlib import Path

from jobs_agent.core import Job
from jobs_agent.publish import digest_markdown, publish_jobs, telegram_message


class PublishTests(unittest.TestCase):
    def make_job(self, job_id: str, title: str) -> Job:
        return Job(
            id=job_id, title=title, company="Acme", location="Berlin, Deutschland",
            url=f"https://example.test/{job_id}", description="Python",
            source="fixture", role_type="werkstudent", category="cs", score=90,
            reasons=["Werkstudent role", "Computer-science relevance"],
        )

    def test_publish_writes_static_dashboard_and_reports_only_new_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory) / "docs"
            docs.mkdir()
            (docs / "jobs.json").write_text(json.dumps([{"id": "old"}]))

            jobs = [self.make_job("old", "Old role"), self.make_job("new", "New role")]
            new_jobs = publish_jobs(jobs, docs)

            self.assertEqual([job.id for job in new_jobs], ["new"])
            exported = json.loads((docs / "jobs.json").read_text())
            self.assertEqual({job["id"] for job in exported}, {"old", "new"})
            for asset in ("index.html", "app.js", "gmail.js", "styles.css", ".nojekyll"):
                self.assertTrue((docs / asset).exists(), asset)
            app = (docs / "app.js").read_text()
            self.assertIn("jobs.json", app)
            self.assertIn("localStorage", app)
            config = json.loads((docs / "config.json").read_text())
            self.assertEqual(config["title"], "Germany Student Jobs")

    def test_dashboard_has_switch_for_cs_and_general_part_time_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory) / "docs"
            cs_job = self.make_job("cs", "Werkstudent Backend")
            part_time_job = Job(
                id="general", title="Minijob Lagerhelfer", company="Warehouse GmbH",
                location="Hamburg, Deutschland", url="https://example.test/general",
                description="Flexible shifts", source="fixture", role_type="minijob",
                category="part-time", score=70, reasons=["Part-time/minijob role"],
            )
            publish_jobs([cs_job, part_time_job], docs)

            exported = json.loads((docs / "jobs.json").read_text())
            self.assertEqual({job["category"] for job in exported}, {"cs", "part-time"})
            config = json.loads((docs / "config.json").read_text())
            self.assertEqual(
                config["categories"],
                [
                    {"id": "cs", "label": "CS & Tech", "scope": "germany"},
                    {"id": "part-time", "label": "Part-time & Minijob · Leipzig area", "scope": "local"},
                ],
            )
            self.assertIn("data-category", (docs / "app.js").read_text())
            self.assertNotIn("client_secret", json.dumps(config))

    def test_telegram_message_contains_new_roles_and_live_site(self):
        message = telegram_message(
            [self.make_job("new", "Working Student Backend")],
            "https://ot-coder.github.io/germany-cs-jobs-agent/",
        )
        self.assertIn("1 new suitable role", message)
        self.assertIn("Working Student Backend", message)
        self.assertIn("Open dashboard", message)

    def test_telegram_message_labels_general_part_time_jobs(self):
        job = Job(
            id="general", title="Minijob Lagerhelfer", company="Warehouse GmbH",
            location="Hamburg, Deutschland", url="https://example.test/general",
            description="Flexible shifts", source="fixture", role_type="minijob",
            category="part-time", score=70, reasons=["Part-time/minijob role"],
        )
        message = telegram_message([job], "https://example.test")
        self.assertIn("Germany Student Jobs", message)
        self.assertIn("Part-time & Minijob", message)

    def test_telegram_message_reports_daily_scan_without_new_jobs(self):
        message = telegram_message([], "https://example.test", total_jobs=42)
        self.assertIn("Daily scan complete", message)
        self.assertIn("No new suitable roles today", message)
        self.assertIn("42 live matches", message)
        self.assertIn("https://example.test", message)

    def test_digest_markdown_groups_by_category_and_neutralises_markup(self):
        job = self.make_job("x", "Werkstudent <script> @everyone [x](y)")
        body = digest_markdown([job], "https://example.test/", total_jobs=3)
        self.assertIn("### CS & Tech", body)
        self.assertIn("1 new suitable role", body)
        self.assertNotIn("<script>", body)
        self.assertNotIn(" @everyone", body)
        self.assertIn("(https://example.test/x)", body)

    def test_digest_markdown_without_new_jobs(self):
        body = digest_markdown([], "https://example.test/", total_jobs=0)
        self.assertIn("no new suitable roles", body)
        self.assertIn("https://example.test/", body)


if __name__ == "__main__":
    unittest.main()
