from __future__ import annotations

from job_agent.agent.platform_detector import detect_platform
from job_agent.handlers.ashby_handler import AshbyHandler
from job_agent.handlers.bamboo_handler import BambooHandler
from job_agent.handlers.generic_handler import GenericHandler
from job_agent.handlers.greenhouse_handler import GreenhouseHandler
from job_agent.handlers.icims_handler import ICIMSHandler
from job_agent.handlers.jobvite_handler import JobviteHandler
from job_agent.handlers.lever_handler import LeverHandler
from job_agent.handlers.smartrecruiters_handler import SmartRecruitersHandler
from job_agent.handlers.successfactors_handler import SuccessFactorsHandler
from job_agent.handlers.taleo_handler import TaleoHandler
from job_agent.handlers.workday_handler import WorkdayHandler


HANDLER_MAP = {
    "ashby": AshbyHandler,
    "bamboo": BambooHandler,
    "generic": GenericHandler,
    "greenhouse": GreenhouseHandler,
    "icims": ICIMSHandler,
    "jobvite": JobviteHandler,
    "lever": LeverHandler,
    "smartrecruiters": SmartRecruitersHandler,
    "successfactors": SuccessFactorsHandler,
    "taleo": TaleoHandler,
    "workday": WorkdayHandler,
}


class JobAgent:
    def __init__(self, handler_map=None):
        self.handler_map = handler_map or HANDLER_MAP

    def get_handler_class(self, platform: str):
        return self.handler_map.get(platform, self.handler_map["generic"])

    async def run(self, url: str, websocket=None, browser=None):
        platform = detect_platform(url)
        handler_class = self.get_handler_class(platform)
        handler = handler_class(websocket=websocket, browser=browser)
        await handler.send(f"Detected platform: {platform}")
        return await handler.apply(url)

    async def apply(self, url: str, websocket=None, browser=None):
        return await self.run(url, websocket=websocket, browser=browser)
