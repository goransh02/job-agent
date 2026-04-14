import unittest
from unittest.mock import patch

from job_agent.agent.value_resolver import resolve, resolve_field


PROFILE = {
    "profile_id": "candidate-a",
    "first_name": "Goran",
    "last_name": "Ghattani",
    "email": "goran@example.com",
    "phone": {"number": "9999999999", "type": "Mobile", "country_code": "+91"},
    "address": {
        "line1": "42 Example Street",
        "city": "Bengaluru",
        "state": "Karnataka",
        "zip": "560001",
        "country": "India",
    },
    "job_source": "LinkedIn",
    "skills": ["Python", "FastAPI"],
    "resume_path": "/tmp/resume.pdf",
    "cover_letter_path": "/tmp/cover-letter.pdf",
}


class ValueResolverTests(unittest.TestCase):
    def test_resolves_direct_profile_values(self):
        with patch(
            "job_agent.agent.value_resolver.search_similar",
            return_value=None,
        ), patch(
            "job_agent.agent.value_resolver.ask_llm",
            return_value=None,
        ), patch(
            "job_agent.agent.value_resolver.ask_llm_json",
            return_value=None,
        ):
            self.assertEqual(resolve("first_name", "First Name", profile=PROFILE), "Goran")
            self.assertEqual(resolve("phone", "Phone", profile=PROFILE), "9999999999")
            self.assertEqual(resolve("phone_device_type", "Phone Device Type", profile=PROFILE), "Mobile")
            self.assertEqual(resolve("job_source", "How Did You Hear About Us?", profile=PROFILE), "LinkedIn")
            self.assertEqual(resolve("skills", "Skills", profile=PROFILE), "Python, FastAPI")
            self.assertEqual(resolve("country", "Country", profile=PROFILE), "India +91")
            self.assertEqual(resolve("cover_letter", "Cover Letter", profile=PROFILE), "/tmp/cover-letter.pdf")

    def test_builds_full_name_when_needed(self):
        profile = {"profile_id": "candidate-a", "first_name": "Goran", "last_name": "Ghattani"}

        with patch(
            "job_agent.agent.value_resolver.search_similar",
            return_value=None,
        ), patch(
            "job_agent.agent.value_resolver.ask_llm",
            return_value=None,
        ), patch(
            "job_agent.agent.value_resolver.ask_llm_json",
            return_value=None,
        ):
            self.assertEqual(resolve("full_name", "Full Name", profile=profile), "Goran Ghattani")

    def test_uses_learned_answers_before_reasoning(self):
        with patch(
            "job_agent.agent.value_resolver.search_similar",
            return_value="2 weeks",
        ) as search_similar, patch(
            "job_agent.agent.value_resolver.ask_llm",
            return_value="Should not be used",
        ) as ask_llm, patch(
            "job_agent.agent.value_resolver.ask_llm_json",
            return_value={"answer": "Should not be used", "confidence": 1},
        ) as ask_llm_json:
            answer = resolve("notice_period", "Notice period", profile={"profile_id": "candidate-a"})

        self.assertEqual(answer, "2 weeks")
        search_similar.assert_called_once_with("Notice period", profile_id="candidate-a")
        ask_llm.assert_not_called()
        ask_llm_json.assert_not_called()

    def test_returns_profile_knowledge_before_freeform_llm(self):
        with patch(
            "job_agent.agent.value_resolver.search_profile_knowledge",
            return_value=[],
        ), patch(
            "job_agent.agent.value_resolver.build_profile_context",
            return_value="- [Experience] Built backend systems at Air India",
        ), patch(
            "job_agent.agent.value_resolver.ask_llm_json",
            return_value={"answer": "Air India", "confidence": 0.88},
        ):
            resolution = resolve_field(
                "company_name",
                "Current company",
                profile={"profile_id": "candidate-a"},
                profile_id="candidate-a",
            )

        self.assertEqual(resolution["value"], "Air India")
        self.assertEqual(resolution["source"], "groq_reasoning")
        self.assertGreater(resolution["confidence"], 0.8)

    def test_returns_none_when_reasoning_reports_unknown(self):
        with patch(
            "job_agent.agent.value_resolver.search_profile_knowledge",
            return_value=[],
        ), patch(
            "job_agent.agent.value_resolver.build_profile_context",
            return_value=None,
        ), patch(
            "job_agent.agent.value_resolver.ask_llm_json",
            return_value={"answer": "UNKNOWN", "confidence": 0.1},
        ), patch(
            "job_agent.agent.value_resolver.ask_llm",
            return_value="UNKNOWN",
        ):
            self.assertIsNone(resolve("unknown", "Favorite color", profile={"profile_id": "candidate-a"}))

    def test_does_not_reuse_learned_notice_period_for_experience_dates(self):
        with patch(
            "job_agent.agent.value_resolver.search_similar",
            return_value="60 days",
        ) as search_similar, patch(
            "job_agent.agent.value_resolver.search_profile_knowledge",
            return_value=[],
        ), patch(
            "job_agent.agent.value_resolver.build_profile_context",
            return_value=None,
        ), patch(
            "job_agent.agent.value_resolver.ask_llm_json",
            return_value={"answer": "UNKNOWN", "confidence": 0.1},
        ), patch(
            "job_agent.agent.value_resolver.ask_llm",
            return_value=None,
        ):
            answer = resolve("start_date_year", "Start date year", profile={"profile_id": "candidate-a"})

        self.assertIsNone(answer)
        search_similar.assert_not_called()
