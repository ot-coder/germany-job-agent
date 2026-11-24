import tomllib
import unittest
from pathlib import Path

WORKFLOWS = Path(".github/workflows")


class WorkflowTests(unittest.TestCase):
    def test_manual_dispatch_can_force_a_test_notification(self):
        workflow = (WORKFLOWS / "refresh-jobs.yml").read_text()
        self.assertIn("send_test_notification:", workflow)
        self.assertIn("inputs.send_test_notification", workflow)
        self.assertIn("Cloud workflow test", workflow)

    def test_daily_digest_is_delivered_as_github_issue(self):
        workflow = (WORKFLOWS / "refresh-jobs.yml").read_text()
        self.assertIn("issues: write", workflow)
        self.assertIn("gh issue create", workflow)
        self.assertIn("--assignee \"$OWNER\"", workflow)
        self.assertIn("--digest .out/digest.md", workflow)

    def test_site_url_comes_from_pages_not_a_hardcoded_owner(self):
        workflow = (WORKFLOWS / "refresh-jobs.yml").read_text()
        self.assertIn("steps.pages.outputs.base_url", workflow)
        self.assertNotIn("ot-coder.github.io", workflow)
        self.assertLess(workflow.index("id: pages"), workflow.index("jobs_agent publish"))

    def test_telegram_stays_optional(self):
        workflow = (WORKFLOWS / "refresh-jobs.yml").read_text()
        self.assertIn('[ -n "$TELEGRAM_BOT_TOKEN" ]', workflow)

    def test_setup_form_passes_inputs_through_env_not_inline(self):
        workflow = (WORKFLOWS / "setup.yml").read_text()
        run_lines = [line for line in workflow.splitlines() if "python -m jobs_agent setup" in line]
        self.assertTrue(run_lines)
        self.assertTrue(all("${{" not in line for line in run_lines))
        for name in ("field", "city", "radius_km", "level", "scope", "local_part_time"):
            self.assertIn(f"{name}:", workflow)

    def test_repository_config_is_valid_toml(self):
        with open("jobs-agent.toml", "rb") as handle:
            self.assertIn("categories", tomllib.load(handle))


if __name__ == "__main__":
    unittest.main()
