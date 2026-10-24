"""Type normalization and validation for extracted values. Bad values are rejected, never guessed."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import phonenumbers
from email_validator import EmailNotValidError, validate_email

from app.crawl.urlnorm import normalize_url
from app.spec.models import FieldSpec, FieldType

WS_RE = re.compile(r"\s+")
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d.%m.%Y", "%B %d, %Y", "%d %B %Y", "%Y-%m", "%Y")


class InvalidValue(ValueError):
    pass


def clean_text(value: Any, max_length: int = 2000) -> str:
    text = WS_RE.sub(" ", str(value)).strip()
    return text[:max_length]


def normalize_value(spec: FieldSpec, value: Any) -> Any:
    """Return the canonical value for the field type or raise InvalidValue."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise InvalidValue("empty")
    t = spec.type
    if t == FieldType.list:
        items = value if isinstance(value, list) else re.split(r"[;,\n]", str(value))
        out = []
        for item in items:
            text = clean_text(item, 300)
            if text and text not in out:
                out.append(text)
        if not out:
            raise InvalidValue("empty list")
        return out[:50]
    if isinstance(value, list):
        value = value[0] if value else None
        if value is None:
            raise InvalidValue("empty")
    if t in (FieldType.string, FieldType.text):
        return clean_text(value, spec.max_length)
    if t == FieldType.url:
        url = normalize_url(str(value).strip())
        if not url:
            raise InvalidValue(f"not an http(s) URL: {str(value)[:80]}")
        return url
    if t == FieldType.email:
        raw = str(value).strip().removeprefix("mailto:").split("?")[0]
        try:
            return validate_email(raw, check_deliverability=False).normalized
        except EmailNotValidError as exc:
            raise InvalidValue(str(exc)) from None
    if t == FieldType.phone:
        raw = str(value).strip().removeprefix("tel:")
        try:
            num = phonenumbers.parse(raw, None if raw.startswith("+") else "US")
        except phonenumbers.NumberParseException as exc:
            raise InvalidValue(str(exc)) from None
        if not phonenumbers.is_possible_number(num):
            raise InvalidValue("not a possible phone number")
        return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    if t in (FieldType.number, FieldType.integer):
        text = str(value).strip().replace(",", "").replace(" ", "")
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            raise InvalidValue(f"not a number: {str(value)[:40]}")
        num = float(match.group())
        if t == FieldType.integer:
            if not num.is_integer():
                raise InvalidValue("not an integer")
            return int(num)
        return num
    if t == FieldType.date:
        if isinstance(value, (date, datetime)):
            return value.isoformat()[:10]
        text = clean_text(value, 60)
        try:
            return datetime.fromisoformat(text).date().isoformat()
        except ValueError:
            pass
        for fmt in DATE_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt).date()
            except ValueError:
                continue
            # A bare year or year-month stays as written instead of inventing a day.
            return text if fmt in ("%Y", "%Y-%m") else parsed.isoformat()
        raise InvalidValue(f"not a date: {text}")
    if t == FieldType.boolean:
        text = str(value).strip().lower()
        if text in ("true", "yes", "1", "y"):
            return True
        if text in ("false", "no", "0", "n"):
            return False
        raise InvalidValue("not a boolean")
    raise InvalidValue(f"unsupported type {t}")
