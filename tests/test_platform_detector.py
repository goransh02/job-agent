import unittest

from job_agent.agent.platform_detector import detect_platform


class PlatformDetectorTests(unittest.TestCase):
    def test_detects_known_platforms(self):
        cases = {
            "https://jobs.lever.co/example": "lever",
            "https://boards.greenhouse.io/example": "greenhouse",
            "https://example.smartrecruiters.com/job": "smartrecruiters",
            "https://example.workdayjobs.com/apply": "workday",
        }

        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(detect_platform(url), expected)

    def test_returns_generic_for_unknown_platforms(self):
        self.assertEqual(detect_platform("https://example.com/careers"), "generic")
