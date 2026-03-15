from pydantic import BaseModel
from typing import List, Optional


class Phone(BaseModel):

    country_code: str
    number: str
    type: str


class Address(BaseModel):

    line1: str
    line2: Optional[str]
    city: str
    state: str
    zip: str
    country: str


class UserProfile(BaseModel):

    first_name: str
    middle_name: Optional[str]
    last_name: str
    full_name: str

    email: str

    phone: Phone
    address: Address

    linkedin: str
    github: str
    portfolio: Optional[str]

    experience_years: int
    skills: List[str]

    notice_period: str

    resume_path: str