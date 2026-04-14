import unittest
from unittest.mock import patch

from job_agent.services.extension_service import build_extension_fill_plan


class ExtensionServiceTests(unittest.TestCase):
    def test_build_fill_plan_blocks_manual_upload_fields(self):
        plan = build_extension_fill_plan(
            "https://example.com/job",
            [
                {
                    "field_id": "resume-1",
                    "label": "Resume/CV*",
                    "tag_name": "input",
                    "input_type": "file",
                    "role": "",
                    "required": True,
                }
            ],
            profile={},
        )

        self.assertEqual(plan["stats"]["fills"], 0)
        self.assertEqual(plan["stats"]["blocked"], 1)
        self.assertEqual(plan["blocked"][0]["reason"], "manual_upload_required")

    def test_build_fill_plan_uses_resolver_for_regular_fields(self):
        with patch(
            "job_agent.services.extension_service.resolve",
            side_effect=["Goran", "India +91", None],
        ) as resolve:
            plan = build_extension_fill_plan(
                "https://example.com/job",
                [
                    {
                        "field_id": "f1",
                        "label": "First Name*",
                        "tag_name": "input",
                        "input_type": "text",
                        "role": "",
                        "required": True,
                    },
                    {
                        "field_id": "f2",
                        "label": "Country*",
                        "tag_name": "select",
                        "input_type": "",
                        "role": "",
                        "required": True,
                        "options": ["India +91", "United States +1"],
                    },
                    {
                        "field_id": "f3",
                        "label": "Custom question",
                        "tag_name": "input",
                        "input_type": "text",
                        "role": "",
                        "required": True,
                    },
                ],
                profile={"profile_id": "candidate-a"},
                profile_id="candidate-a",
            )

        self.assertEqual(plan["stats"]["fills"], 2)
        self.assertEqual(plan["stats"]["blocked"], 1)
        self.assertEqual(plan["profile_id"], "candidate-a")
        self.assertEqual(plan["fills"][0]["value"], "Goran")
        self.assertEqual(plan["fills"][1]["value"], "India +91")
        self.assertEqual(plan["blocked"][0]["reason"], "missing_value")
        resolve.assert_any_call("first_name", "First Name*", profile={"profile_id": "candidate-a"}, profile_id="candidate-a")

    def test_build_fill_plan_skips_optional_unknown_fields(self):
        with patch(
            "job_agent.services.extension_service.resolve",
            return_value=None,
        ):
            plan = build_extension_fill_plan(
                "https://example.com/job",
                [
                    {
                        "field_id": "f1",
                        "label": "Other social network (if applicable)",
                        "tag_name": "input",
                        "input_type": "text",
                        "role": "",
                        "required": False,
                    }
                ],
                profile={},
            )

        self.assertEqual(plan["stats"]["blocked"], 0)
        self.assertEqual(plan["stats"]["skipped"], 1)
        self.assertEqual(plan["skipped"][0]["reason"], "missing_value")
