FIELD_PATTERNS = [
    ("job_source", ("how did you hear about us", "how did you hear", "where did you hear", "source")),
    ("company_name", ("company name", "employer", "organization")),
    ("job_title", ("job title", "position title", "role title", "title")),
    ("start_date_month", ("start date month", "employment start month", "from month")),
    ("start_date_year", ("start date year", "employment start year", "from year")),
    ("end_date_month", ("end date month", "employment end month", "to month")),
    ("end_date_year", ("end date year", "employment end year", "to year")),
    ("current_role", ("current role", "currently work here", "currently employed here", "i currently work here")),
    ("summary", ("tell us more about you", "about you", "professional summary", "summary", "profile summary", "bio")),
    ("cover_letter", ("cover letter",)),
    ("resume", ("resume", "curriculum vitae", "cv")),
    ("portfolio", ("portfolio", "personal website")),
    ("linkedin", ("linkedin",)),
    ("github", ("github",)),
    ("first_name", ("first name", "given name")),
    ("last_name", ("last name", "surname", "family name")),
    ("full_name", ("full name", "legal name")),
    ("email", ("email", "e-mail")),
    ("phone_device_type", ("phone device type", "device type", "type of device")),
    ("phone", ("phone", "mobile", "telephone")),
    ("location", ("present location", "current location", "location (city)", "location")),
    ("address_line2", ("address line 2", "apartment", "suite", "unit")),
    ("address_line1", ("address line 1", "street address", "mailing address", "address")),
    ("city", ("city", "town")),
    ("state", ("state", "province", "region")),
    ("zip", ("zip", "postal code", "postcode")),
    ("country", ("country",)),
    ("experience_years", ("years of experience", "experience in years", "total experience")),
    ("skills", ("skills", "technologies", "tech stack")),
    ("notice_period", ("notice period", "availability to join", "joining period", "notice")),
]


def classify(label: str | None) -> str:
    normalized = " ".join((label or "").strip().lower().replace("_", " ").split())

    for field_type, patterns in FIELD_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            return field_type

    return "unknown"
