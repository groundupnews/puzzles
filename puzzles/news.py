"""Stories from the GroundUp news site, to send puzzle players on to it.

The news site sends no CORS headers, so the stories are fetched here,
server-side, and cached. A fetch that fails falls back to the last good
copy, or to nothing: a slow or broken news site must never break a game.
"""

import json
import re
from html import unescape
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from django.conf import settings
from django.core.cache import cache

TIMEOUT = 2.5  # seconds
FRESH = 10 * 60
STALE = 24 * 60 * 60

# Everything that a fetch from a misbehaving site can raise: network
# errors and timeouts are OSErrors, the rest is a response we can't read.
FETCH_ERRORS = (OSError, ValueError, KeyError, TypeError, ElementTree.ParseError)


def _get(url):
    request = Request(url, headers={"User-Agent": "GroundUp Puzzles"})
    with urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def _cached(key, fetch):
    """fetch()'s result, at most FRESH seconds old; the last good one (up
    to STALE old) when fetch() fails. A failure is cached too, so a news
    site that's down isn't asked again on every page."""
    value = cache.get(key)
    if value is None:
        try:
            value = fetch()
        except FETCH_ERRORS:
            value = cache.get(key + ":stale", [])
        else:
            cache.set(key + ":stale", value, STALE)
        cache.set(key, value, FRESH)
    return value


def _ranked(path):
    """One of the news site's ranked lists of the past week's articles,
    top first: [{"title", "url"}]."""

    def fetch():
        data = json.loads(_get(settings.NEWS_SITE_URL + path))
        return [{"title": a["title"], "url": a["url"]} for a in data["articles"]]

    return _cached("news:" + path, fetch)


def most_read():
    """The past week's articles with the most readers."""
    return _ranked("/api/most-popular/")


def most_deeply_read():
    """The past week's articles readers spent longest on: the ones that
    hold people, which suits players who've just spent a while on a
    puzzle."""
    return _ranked("/api/most-deeply-read/")


def picture(url):
    """The picture a news-site article shows on social media, or "". The
    ranked lists don't include one, so it's read off the article's page;
    an article's picture rarely changes, so it's kept for a day."""
    key = "news:picture:" + url
    value = cache.get(key)
    if value is None:
        try:
            value = article(url)["image"]
        except FETCH_ERRORS:
            value = ""
        cache.set(key, value, STALE)
    return value


def latest():
    """The newest articles, in the news site's own order (sticky ones
    first), from its RSS feed: [{"title", "url", "summary", "image",
    "category"}]."""

    def fetch():
        feed = ElementTree.fromstring(_get(settings.NEWS_SITE_URL + "/sitenews/rss/"))
        return [
            {
                "title": item.findtext("title", ""),
                "url": item.findtext("link", ""),
                "summary": item.findtext("description", ""),
                "image": item.find("enclosure").get("url", "")
                if item.find("enclosure") is not None
                else "",
                "category": item.findtext("category", ""),
            }
            for item in feed.iter("item")
        ]

    return _cached("news:latest", fetch)


def is_news_url(url):
    """True for a link to a page on the news site."""
    parts = urlsplit(url)
    site = urlsplit(settings.NEWS_SITE_URL)
    return parts.scheme in ("http", "https") and parts.netloc.removeprefix("www.") == site.netloc


def _meta(page, name):
    match = re.search(rf'<meta (?:property|name)="{re.escape(name)}" content="([^"]*)"', page)
    return unescape(match.group(1)).strip() if match else ""


def article(url):
    """The headline and picture of a news-site article, from the tags its
    page carries for social media: {"title", "image"}. Only the news site
    is asked -- this is not a general-purpose fetcher. Raises ValueError
    for any other URL, and one of FETCH_ERRORS if the page can't be had."""
    if not is_news_url(url):
        raise ValueError(f"not a {settings.NEWS_SITE_URL} link")
    page = _get(url).decode("utf-8", "replace")
    return {
        "title": _meta(page, "og:title") or _meta(page, "twitter:title"),
        "image": _meta(page, "twitter:image") or _meta(page, "og:image"),
    }


# The news site's region pages, for a Streetwise district: its metro where
# the news site has a page for it, else its province. Keyed by the IEC's
# municipality code or province name; the paths are the news site's own,
# spelling quirks and all.
REGIONS = {
    "CPT": ("Cape Town", "South Africa/Western Cape/Cape Town"),
    "JHB": ("Johannesburg", "South Africa/Gauteng/Johannesburg"),
    "TSH": ("Pretoria", "South Africa/Gauteng/Pretoria"),
    "ETH": ("Durban", "South Africa/Kwazulu-Natal/Durban"),
    "NMA": ("Gqeberha", "South Africa/Eastern Cape/Gqeberha"),
    "BUF": ("East London", "South Africa/Eastern Cape/East London"),
    "MAN": ("Bloemfontein", "South Africa/Free State/Bloemfontein"),
    "Eastern Cape": ("the Eastern Cape", "South Africa/Eastern Cape"),
    "Free State": ("the Free State", "South Africa/Free State"),
    "Gauteng": ("Gauteng", "South Africa/Gauteng"),
    "KwaZulu-Natal": ("KwaZulu-Natal", "South Africa/Kwazulu-Natal"),
    "Limpopo": ("Limpopo", "South Africa/Limpopo"),
    "Mpumalanga": ("Mpumalanga", "SouthAfrica/Mpumalanga"),
    "North West": ("North West", "South Africa/North West"),
    "Northern Cape": ("the Northern Cape", "SouthAfrica/Northern Cape"),
    "Western Cape": ("the Western Cape", "South Africa/Western Cape"),
}


def region(municipality_code, province):
    """GroundUp's reporting from a place: {"place", "url"}, or None."""
    found = REGIONS.get(municipality_code) or REGIONS.get(province)
    if found is None:
        return None
    place, path = found
    return {"place": place, "url": f"{settings.NEWS_SITE_URL}/region/{quote(path)}"}
