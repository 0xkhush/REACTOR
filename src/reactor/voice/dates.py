"""Parse calendar days without assigning a missing user-requested year."""

import re
from datetime import datetime


def calendar_day(value):
    if not isinstance(value, str):
        return None
    text = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", value.strip(), flags=re.I)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            date = datetime.strptime(text, fmt)
            return date.month, date.day, date.year
        except ValueError:
            pass
    for fmt in ("%m/%d", "%B %d", "%b %d"):
        try:
            date = datetime.strptime(text + " 2000", fmt + " %Y")
            return date.month, date.day, None
        except ValueError:
            pass
    return None
