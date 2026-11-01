"""
utils.py - Small helper functions used across the project.
"""
import re
from datetime import datetime, timedelta, timezone

# Nigeria uses West Africa Time (UTC+1) all year, with no daylight saving.
# Render's servers run on UTC, so we always calculate "today" in WAT.
WAT = timezone(timedelta(hours=1), "WAT")


def now_wat():
    """Current date and time in Nigeria (stored without timezone info in the database)."""
    return datetime.now(WAT).replace(tzinfo=None)


def today_wat():
    """Today's date in Nigeria."""
    return now_wat().date()


def normalize_phone(raw):
    """
    Convert any common Nigerian phone format to one standard format: +234XXXXXXXXXX

        08031234567     -> +2348031234567
        +2348031234567  -> +2348031234567
        2348031234567   -> +2348031234567
        8031234567      -> +2348031234567
        0803 123 4567   -> +2348031234567

    Returns None if the input is empty or not a valid Nigerian mobile number.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))   # keep numbers only

    if digits.startswith("234") and len(digits) == 13:
        local = digits[3:]
    elif digits.startswith("0") and len(digits) == 11:
        local = digits[1:]
    elif len(digits) == 10 and digits[0] in "789":
        local = digits
    else:
        return None

    return "+234" + local


def format_phone_display(phone):
    """+2348031234567 -> 0803 123 4567 (friendlier for display)."""
    if not phone or not phone.startswith("+234") or len(phone) != 14:
        return phone or ""
    local = "0" + phone[4:]
    return f"{local[:4]} {local[4:7]} {local[7:]}"
