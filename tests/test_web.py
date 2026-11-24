import unittest

from jobs_agent.web import render_digest


JOBS = [{
    "id": "abc", "title": "Junior <Developer>", "company": "Acme & Co",
    "location": "Berlin", "url": "https://example.com/job", "description": "Python",
    "source": "test", "role_family": "CORE_TECH", "remote": False,
    "published_at": "", "score": 81, "reasons": ["Credible Core Tech entry point"],
    "first_seen_at": "2026-01-01T00:00:00+00:00", "status": "new",
}]


class WebTests(unittest.TestCase):
    def test_digest_contains_ranked_markdown_link(self):
        digest = render_digest(JOBS, new_count=1)
        self.assertIn("1 new suitable role", digest)
        self.assertIn("[Junior <Developer>](https://example.com/job)", digest)
        self.assertIn("81/100", digest)


if __name__ == "__main__":
    unittest.main()
