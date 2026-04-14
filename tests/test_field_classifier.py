import unittest

from job_agent.agent.field_classifier import classify


class FieldClassifierTests(unittest.TestCase):
    def test_start_date_year_is_not_notice_period(self):
        self.assertEqual(classify("Start date year"), "start_date_year")

    def test_notice_period_is_classified_separately(self):
        self.assertEqual(classify("Notice period"), "notice_period")

    def test_present_location_is_classified_as_location(self):
        self.assertEqual(classify("Present location"), "location")

    def test_about_you_is_classified_as_summary(self):
        self.assertEqual(classify("Tell us more about you"), "summary")
