import unittest
from unittest.mock import patch

from job_agent.agent.job_agent import JobAgent


class FakeRunner:
    instances = []

    def __init__(self, *, platform, websocket=None, browser=None, auto_submit=None):
        self.platform = platform
        self.websocket = websocket
        self.browser = browser
        self.auto_submit = auto_submit
        self.sent_messages = []
        self.run_calls = []
        FakeRunner.instances.append(self)

    def build_initial_state(self, *, job_url, profile_id, application_id=None, continued=False):
        return {
            "application_id": application_id or "app-123",
            "profile_id": profile_id or "default",
            "job_url": job_url,
            "continued": continued,
            "result": {
                "platform": self.platform,
                "url": job_url,
                "continued": continued,
                "stopped_reason": None,
            },
        }

    async def send(self, message, event_type="status", **payload):
        self.sent_messages.append((event_type, message, payload))

    async def run(self, state):
        self.run_calls.append(state)
        return {
            "platform": self.platform,
            "url": state["job_url"],
            "application_id": state["application_id"],
            "continued": state.get("continued", False),
        }


class JobAgentTests(unittest.IsolatedAsyncioTestCase):
    @patch("job_agent.agent.job_agent.ApplicationGraphRunner", FakeRunner)
    async def test_run_uses_platform_specific_graph_runner(self):
        agent = JobAgent()

        result = await agent.run("https://company.workdayjobs.com/en-US/job", profile_id="candidate-a")

        self.assertEqual(result["platform"], "workday")
        self.assertEqual(result["application_id"], "app-123")
        self.assertEqual(FakeRunner.instances[-1].sent_messages[0][1], "Detected platform: workday")
        self.assertEqual(FakeRunner.instances[-1].run_calls[0]["profile_id"], "candidate-a")

    @patch("job_agent.agent.job_agent.ApplicationGraphRunner", FakeRunner)
    @patch(
        "job_agent.agent.job_agent.load_application_state",
        return_value={
            "application_id": "app-123",
            "profile_id": "candidate-a",
            "job_url": "https://example.com/jobs/123",
            "result": {"platform": "generic", "url": "https://example.com/jobs/123"},
        },
    )
    async def test_continue_run_uses_persisted_application_state(self, load_application_state):
        agent = JobAgent()
        await agent.run("https://example.com/jobs/123", profile_id="candidate-a")
        result = await agent.continue_run(profile_id="candidate-a")

        self.assertTrue(result["continued"])
        self.assertEqual(result["application_id"], "app-123")
        load_application_state.assert_called_once_with("app-123")
