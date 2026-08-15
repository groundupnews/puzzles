from django import template

register = template.Library()

# Order matters: browsers that also match an earlier marker (e.g. Chrome and
# Edge both contain "Safari/") must be listed before it.
_BROWSERS = [
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
]

# Android UAs also contain "Linux", so it must be listed before Linux.
_OPERATING_SYSTEMS = [
    ("Windows", "Windows"),
    ("Android", "Android"),
    ("iPhone", "iOS"),
    ("iPad", "iOS"),
    ("Mac OS X", "macOS"),
    ("Linux", "Linux"),
]


@register.filter
def browser_summary(user_agent):
    if not user_agent:
        return "Unknown"
    browser = next((name for marker, name in _BROWSERS if marker in user_agent), "Unknown browser")
    os_name = next((name for marker, name in _OPERATING_SYSTEMS if marker in user_agent), "unknown OS")
    return f"{browser} on {os_name}"
