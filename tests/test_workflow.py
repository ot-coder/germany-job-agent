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

    def test_tests_run_in_ci_not_in_the_daily_deploy(self):
        refresh = (WORKFLOWS / "refresh-jobs.yml").read_text()
        self.assertNotIn("unittest", refresh)
        ci = (WORKFLOWS / "ci.yml").read_text()
        self.assertIn("push:", ci)
        self.assertIn("pull_request:", ci)
        self.assertIn("python -m unittest discover -s tests -v", ci)

    def test_deploy_waits_for_pages_instead_of_failing_in_new_copies(self):
        refresh = (WORKFLOWS / "refresh-jobs.yml").read_text()
        self.assertLess(refresh.index("id: ready"), refresh.index("id: pages"))
        after_gate = refresh[refresh.index("id: ready"):]
        self.assertNotIn("steps.gate.outputs.run", after_gate)

    def test_copies_skip_until_setup_replaces_the_authors_config(self):
        refresh = (WORKFLOWS / "refresh-jobs.yml").read_text()
        marker = "project author's search"
        self.assertIn(f'grep -q "{marker}" jobs-agent.toml', refresh)
        self.assertIn(".is_template", refresh)
        # The author's config carries the marker; the setup form never writes it.
        self.assertIn(marker, Path("tests/fixtures/default-jobs-agent.toml").read_text())
        from jobs_agent.setup import build_config
        self.assertNotIn(marker, build_config("software", "Leipzig"))

    def test_setup_deploys_in_the_same_run_through_the_refresh_workflow(self):
        setup = (WORKFLOWS / "setup.yml").read_text()
        refresh = (WORKFLOWS / "refresh-jobs.yml").read_text()
        # No deploy (or dispatch) of its own: it calls the reusable refresh workflow,
        # which builds, uploads the Pages artifact and deploys in one job.
        for absent in ("actions/deploy-pages", "actions/upload-pages-artifact", "gh workflow run"):
            self.assertNotIn(absent, setup)
        deploy_job = setup[setup.index("\n  deploy:"):]
        self.assertIn("needs: setup", deploy_job)
        self.assertIn("uses: ./.github/workflows/refresh-jobs.yml", deploy_job)
        self.assertIn("send_test_notification: true", deploy_job)
        self.assertIn("secrets: inherit", deploy_job)
        for permission in ("contents: write", "pages: write", "id-token: write", "issues: write", "actions: read"):
            self.assertIn(permission, deploy_job)
            self.assertIn(permission, refresh)
        self.assertIn("workflow_call:", refresh)
        self.assertLess(refresh.index("uses: actions/upload-pages-artifact"), refresh.index("uses: actions/deploy-pages"))

    def test_deploy_runs_in_its_own_job_after_the_upload(self):
        refresh = (WORKFLOWS / "refresh-jobs.yml").read_text()
        refresh_job = refresh[refresh.index("\n  refresh:"):refresh.index("\n  deploy:")]
        deploy_job = refresh[refresh.index("\n  deploy:"):]
        # actions/deploy-pages#451: deploying right after the upload in the same job can find 0 artifacts.
        self.assertIn("uses: actions/upload-pages-artifact", refresh_job)
        self.assertNotIn("uses: actions/deploy-pages", refresh_job)
        self.assertNotIn("environment:", refresh_job)
        self.assertIn("run: ${{ steps.ready.outputs.run }}", refresh_job)
        for line in ("needs: refresh", "if: needs.refresh.outputs.run == 'true'", "runs-on: ubuntu-latest",
                     "pages: write", "id-token: write", "name: github-pages",
                     "url: ${{ steps.deployment.outputs.page_url }}", "id: deployment", "uses: actions/deploy-pages@v5"):
            self.assertIn(line, deploy_job)
        self.assertEqual(deploy_job.count("- name:") + deploy_job.count("- uses:"), 1)  # its only step

    def test_called_refresh_builds_the_config_setup_just_pushed(self):
        refresh = (WORKFLOWS / "refresh-jobs.yml").read_text()
        self.assertIn("ref: ${{ github.ref }}", refresh)
        self.assertNotIn("github.event_name == 'workflow_dispatch' && inputs.send_test_notification", refresh)

    def test_setup_does_not_hold_the_refresh_concurrency_group_for_the_whole_run(self):
        setup = (WORKFLOWS / "setup.yml").read_text()
        top_level = setup[:setup.index("\njobs:")]
        self.assertNotIn("concurrency:", top_level)  # would deadlock with refresh-jobs.yml
        self.assertIn("group: jobs-dashboard", setup)

    def test_actions_are_on_node24_majors(self):
        minimum = {"actions/checkout": 7, "actions/setup-python": 7, "actions/configure-pages": 6,
                   "actions/upload-pages-artifact": 5, "actions/deploy-pages": 5}
        for path in WORKFLOWS.glob("*.yml"):
            for line in path.read_text().splitlines():
                if "uses: actions/" not in line:
                    continue
                action, version = line.split("uses:", 1)[1].strip().split("@")
                with self.subTest(file=path.name, action=action):
                    self.assertGreaterEqual(int(version.lstrip("v").split(".")[0]), minimum[action])

    def test_repository_config_is_valid_toml(self):
        with open("jobs-agent.toml", "rb") as handle:
            self.assertIn("categories", tomllib.load(handle))


if __name__ == "__main__":
    unittest.main()
