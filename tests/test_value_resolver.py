import unittest
from unittest.mock import patch

from job_agent.agent.value_resolver import resolve


PROFILE = {
    "first_name": "Goran",
    "last_name": "Ghattani",
    "email": "goran@example.com",
    "phone": {"number": "9999999999"},
    "address": {
        "line1": "42 Example Street",
        "city": "Bengaluru",
        "state": "Karnataka",
        "zip": "560001",
        "country": "India",
    },
    "skills": ["Python", "FastAPI"],
    "resume_path": "/tmp/resume.pdf",
}


class ValueResolverTests(unittest.TestCase):
    def test_resolves_direct_profile_values(self):
        with patch(
            "job_agent.agent.value_resolver.search_similar",
            return_value=None,
        ), patch(
            "job_agent.agent.value_resolver.ask_llm",
            return_value=None,
        ):
            self.assertEqual(resolve("first_name", "First Name", profile=PROFILE), "Goran")
            self.assertEqual(resolve("phone", "Phone", profile=PROFILE), "9999999999")
            self.assertEqual(resolve("skills", "Skills", profile=PROFILE), "Python, FastAPI")

    def test_builds_full_name_when_needed(self):
        profile = {"first_name": "Goran", "last_name": "Ghattani"}

        with patch(
            "job_agent.agent.value_resolver.search_similar",
            return_value=None,
        ), patch(
            "job_agent.agent.value_resolver.ask_llm",
            return_value=None,
        ):
            self.assertEqual(resolve("full_name", "Full Name", profile=profile), "Goran Ghattani")

    def test_uses_learned_answers_before_llm(self):
        with patch(
            "job_agent.agent.value_resolver.search_similar",
            return_value="2 weeks",
        ) as search_similar, patch(
            "job_agent.agent.value_resolver.ask_llm",
            return_value="Should not be used",
        ) as ask_llm:
            answer = resolve("notice_period", "Notice period", profile={})

        self.assertEqual(answer, "2 weeks")
        search_similar.assert_called_once_with("Notice period")
        ask_llm.assert_not_called()

    def test_returns_none_when_llm_reports_unknown(self):
        with patch(
            "job_agent.agent.value_resolver.search_similar",
            return_value=None,
        ), patch(
            "job_agent.agent.value_resolver.ask_llm",
            return_value="UNKNOWN",
        ):
            self.assertIsNone(resolve("unknown", "Favorite color", profile={}))
