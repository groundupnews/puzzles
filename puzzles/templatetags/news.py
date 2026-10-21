from urllib.parse import urlencode

from django import template

register = template.Library()


@register.filter
def campaign(url, placement):
    """`url` tagged as a click from `placement` on the puzzles site, so
    Matomo's Campaigns report can tell the ways in to the news apart."""
    tag = urlencode({"mtm_campaign": "puzzles", "mtm_kwd": placement})
    return f"{url}{'&' if '?' in url else '?'}{tag}"

