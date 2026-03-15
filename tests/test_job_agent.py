import unittest

from job_agent.agent.job_agent import JobAgent


class RecordingHandler:
    last_instance = None

    def __init__(self, websocket=None, browser=None):
        self.websocket = websocket
        self.browser = browser
        self.events = []
        self.applied_url = None
        type(self).last_instance = self

    async def send(self, message, event_type="status", **payload):
        self.events.append((event_type, message, payload))

    async def apply(self, url):
        self.applied_url = url
        return {"platform": "recording", "url": url}


class GenericRecordingHandler(RecordingHandler):
    pass


class JobAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_uses_platform_specific_handler(self):
        agent = JobAgent(
            handler_map={
                "generic": GenericRecordingHandler,
                "workday": RecordingHandler,
            }
        )

        result = await agent.run("https://company.workdayjobs.com/en-US/job")

        self.assertEqual(result["platform"], "recording")
        self.assertEqual(RecordingHandler.last_instance.applied_url, "https://company.workdayjobs.com/en-US/job")
        self.assertEqual(
            RecordingHandler.last_instance.events[0][1],
            "Detected platform: workday",
        )

    async def test_run_falls_back_to_generic_handler(self):
        agent = JobAgent(handler_map={"generic": GenericRecordingHandler})

        result = await agent.run("https://example.com/jobs/123")

        self.assertEqual(result["platform"], "recording")
        self.assertEqual(
            GenericRecordingHandler.last_instance.events[0][1],
            "Detected platform: generic",
        )
