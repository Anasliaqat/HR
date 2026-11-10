"""Phone-number normalization for candidate matching."""

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat


def normalize_phone_number(
    phone: str | None,
    default_region: str,
) -> str | None:
    """Return a valid international E.164 number, or None when it is invalid."""
    if not phone or not phone.strip():
        return None
    try:
        parsed = phonenumbers.parse(phone, default_region)
    except NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
