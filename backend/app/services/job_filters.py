import re

_TECH_TITLE = re.compile(
    r"\b("
    r"engineer(?:s|ing)?|developer|software|front-?end|back-?end|full[- ]?stack|devops|devsecops|"
    r"security|platform|machine learning|ml|scientist|architect|cloud|sre|site reliability|"
    r"artificial intelligence|ai|mobile|qa|sdet|"
    r"data (?:engineer|scientist|analyst|platform|science|infrastructure)|"
    r"quality (?:assurance|engineer)|technical"
    r")\b",
    re.IGNORECASE,
)
_NOT_TECH_TITLE = re.compile(r"\bdata entry\b", re.IGNORECASE)


def is_tech_title(title: str) -> bool:
    return bool(_TECH_TITLE.search(title)) and not _NOT_TECH_TITLE.search(title)


def listing_key(company: str, title: str, location: str) -> str:
    """Normalized identity used to spot the same role posted at different URLs."""
    parts = (company, title, location)
    return "|".join(re.sub(r"[^a-z0-9]+", " ", part.casefold()).strip() for part in parts)
