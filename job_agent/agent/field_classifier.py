FIELD_PATTERNS = [
    ("resume", ("resume", "curriculum vitae", "cv")),
    ("portfolio", ("portfolio", "personal website")),
    ("linkedin", ("linkedin",)),
    ("github", ("github",)),
    ("first_name", ("first name", "given name")),
    ("last_name", ("last name", "surname", "family name")),
    ("full_name", ("full name", "legal name")),
    ("email", ("email", "e-mail")),
    ("phone", ("phone", "mobile", "telephone")),
    ("address_line2", ("address line 2", "apartment", "suite", "unit")),
    ("address_line1", ("address line 1", "street address", "mailing address", "address")),
    ("city", ("city", "town")),
    ("state", ("state", "province", "region")),
    ("zip", ("zip", "postal code", "postcode")),
    ("country", ("country",)),
    ("experience_years", ("years of experience", "experience in years", "total experience")),
    ("skills", ("skills", "technologies", "tech stack")),
    ("notice_period", ("notice period", "availability", "start date")),
]


def classify(label: str | None) -> str:
    normalized = " ".join((label or "").strip().lower().replace("_", " ").split())

    for field_type, patterns in FIELD_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            return field_type

    return "unknown"
