from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Phone:
    country_code: str
    number: str
    type: str


@dataclass
class Address:
    line1: str
    line2: Optional[str]
    city: str
    state: str
    zip: str
    country: str


@dataclass
class UserProfile:
    profile_id: str = "default"
    first_name: str = ""
    middle_name: Optional[str] = None
    last_name: str = ""
    full_name: str = ""
    email: str = ""
    phone: Phone | None = None
    address: Address | None = None
    linkedin: str = ""
    github: str = ""
    portfolio: Optional[str] = None
    job_source: Optional[str] = None
    experience_years: int = 0
    skills: list[str] | None = None
    notice_period: str = ""
    resume_path: Optional[str] = None
    resume_file_id: Optional[str] = None
    resume_filename: Optional[str] = None
    resume_content_type: Optional[str] = None
    resume_size_bytes: Optional[int] = None
    cover_letter_path: Optional[str] = None
