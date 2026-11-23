# -*- coding: utf-8 -*-
"""Input validation and normalisation shared by the UI and the data layer."""
import re
import uuid

from accqa.revit_compat import to_text, urlparse

CATEGORIES = ["Project Root", "Shared", "WIP", "Published", "Custom"]
CATEGORY_LABELS = {
    "Project Root": u"Project Root",
    "Shared": u"Shared",
    "WIP": u"WIP",
    "Published": u"Published",
    "Custom": u"Custom Folders",
}
EN_DASH = u"\u2013"


class ValidationError(Exception):
    """Raised for user-correctable problems; message_text is safe to show in the UI."""

    def __init__(self, message):
        Exception.__init__(self, message)
        self.message_text = to_text(message)

    def __unicode__(self):
        return self.message_text


def clean(value):
    return to_text(value).strip()


def normalize_name(value):
    """Case-insensitive, whitespace- and dash-insensitive comparison key."""
    text = clean(value).lower()
    text = text.replace(u"\u2013", u"-").replace(u"\u2014", u"-")
    return re.sub(r"\s+", u" ", text)


def normalize_title(value):
    """Comparison key for Revit model titles (drops a trailing .rvt)."""
    text = normalize_name(value)
    if text.endswith(u".rvt"):
        text = text[:-4]
    return text


def make_id(prefix):
    return u"%s_%s" % (prefix, uuid.uuid4().hex[:8])


def require_text(value, label, max_len=200):
    text = clean(value)
    if not text:
        raise ValidationError(u"%s is required." % label)
    if len(text) > max_len:
        raise ValidationError(u"%s is too long (maximum %d characters)." % (label, max_len))
    return text


def canonical_category(value):
    """Return the canonical category name; unknown values become 'Custom'."""
    text = clean(value).lower()
    for cat in CATEGORIES:
        if cat.lower() == text:
            return cat
    if text in (u"root", u"project"):
        return u"Project Root"
    return u"Custom"


def validate_category(value):
    text = clean(value).lower()
    for cat in CATEGORIES:
        if cat.lower() == text:
            return cat
    raise ValidationError(u"Please choose a folder category.")


def validate_url(url):
    """Return the URL (surrounding whitespace removed, nothing else changed) or raise."""
    cleaned = clean(url)
    if not cleaned:
        raise ValidationError(u"ACC URL is required.")
    if re.search(r"\s", cleaned):
        raise ValidationError(
            u"The URL contains spaces or line breaks. Paste one complete URL "
            u"exactly as shown in the browser address bar.")
    try:
        parsed = urlparse(cleaned)
    except Exception:
        raise ValidationError(u"The URL could not be read. Check that it is a complete web address.")
    scheme = (parsed.scheme or u"").lower()
    if scheme not in (u"http", u"https"):
        raise ValidationError(u"The URL must start with http:// or https://")
    if not parsed.netloc or not parsed.hostname:
        raise ValidationError(u"The URL has no web address (host name). Check that it is complete.")
    return cleaned


def is_autodesk_url(url):
    try:
        host = (urlparse(clean(url)).hostname or u"").lower()
    except Exception:
        return False
    return (host == u"autodesk.com" or host.endswith(u".autodesk.com")
            or host.endswith(u".autodesk.com.cn") or host == u"a360.co")


def urls_equal(first, second):
    """Exact comparison (only surrounding whitespace ignored) - URLs are never rewritten."""
    return clean(first) == clean(second)


def project_label(project):
    """'3929 - Name' style label used in lists (en dash like the specification)."""
    number = clean(project.get("project_number"))
    name = clean(project.get("project_name"))
    if number:
        return u"%s %s %s" % (number, EN_DASH, name)
    return name
