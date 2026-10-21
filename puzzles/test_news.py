"""Tests for the stories fetched from the news site (puzzles/news.py).

Worth pinning down: a news site that's down or talking nonsense never
breaks a page, and the article lookup won't fetch anything but the news
site.
"""

import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from puzzles import news

MOST_READ = json.dumps({
    "count": 2,
    "articles": [
        {"slug": "a", "title": "First story", "url": "https://groundup.org.za/article/a/"},
        {"slug": "b", "title": "Second story", "url": "https://groundup.org.za/article/b/"},
    ],
}).encode()

RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>GroundUp News</title>
<item><title>Newest story</title><link>https://groundup.org.za/article/new/</link>
<description>What happened</description>
<enclosure length="1" type="image/jpeg" url="https://groundup.org.za/media/new.jpg"/>
<category>News</category></item>
<item><title>No picture</title><link>https://groundup.org.za/article/plain/</link>
<description>Words only</description></item>
</channel></rss>"""

ARTICLE = b"""<html><head>
<meta property="og:title" content="Mbalula &amp; the music"/>
<meta name="twitter:image" content="https://groundup.org.za/media/m.jpg"/>
</head></html>"""


def fetching(*responses):
    """Patch the network: each fetch gets the next response, and an
    exception in the list is raised instead."""
    return mock.patch.object(news, "_get", side_effect=list(responses))


class NewsTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_most_read(self):
        with fetching(MOST_READ):
            self.assertEqual(news.most_read(), [
                {"title": "First story", "url": "https://groundup.org.za/article/a/"},
                {"title": "Second story", "url": "https://groundup.org.za/article/b/"},
            ])

    def test_latest_reads_the_feed(self):
        with fetching(RSS):
            stories = news.latest()
        self.assertEqual(stories[0], {
            "title": "Newest story",
            "url": "https://groundup.org.za/article/new/",
            "summary": "What happened",
            "image": "https://groundup.org.za/media/new.jpg",
            "category": "News",
        })
        self.assertEqual(stories[1]["image"], "")

    def test_fetched_once_while_fresh(self):
        with fetching(MOST_READ) as get:
            news.most_read()
            news.most_read()
        self.assertEqual(get.call_count, 1)

    def test_site_down_gives_nothing(self):
        with fetching(OSError("timed out")):
            self.assertEqual(news.most_read(), [])

    def test_nonsense_gives_nothing(self):
        with fetching(b"<html>Bad gateway</html>"):
            self.assertEqual(news.most_read(), [])
        cache.clear()
        with fetching(b"<html>Bad gateway"):
            self.assertEqual(news.latest(), [])

    def test_site_down_falls_back_to_last_good_copy(self):
        with fetching(MOST_READ):
            good = news.most_read()
        cache.delete("news:/api/most-popular/")  # as if it had gone stale
        with fetching(OSError("timed out")):
            self.assertEqual(news.most_read(), good)

    def test_article(self):
        with fetching(ARTICLE):
            self.assertEqual(
                news.article("https://groundup.org.za/article/m/"),
                {"title": "Mbalula & the music", "image": "https://groundup.org.za/media/m.jpg"},
            )

    def test_article_fetches_nothing_but_the_news_site(self):
        for url in [
            "http://localhost:8000/admin/",
            "https://groundup.org.za.evil.example/",
            "file:///etc/passwd",
        ]:
            with self.subTest(url=url), fetching() as get:
                with self.assertRaises(ValueError):
                    news.article(url)
                get.assert_not_called()

    def test_www_counts_as_the_news_site(self):
        self.assertTrue(news.is_news_url("https://www.groundup.org.za/article/m/"))



class NewsPanelTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_after_game_lists_most_read_with_campaign_tags(self):
        with fetching(MOST_READ):
            response = self.client.get(reverse("news_after_game"))
        self.assertContains(response, "First story")
        self.assertContains(
            response,
            'href="https://groundup.org.za/article/a/?mtm_campaign=puzzles&amp;mtm_kwd=after-game"',
        )

    def test_after_game_still_offers_the_newsletter_without_stories(self):
        with fetching(OSError("timed out")):
            response = self.client.get(reverse("news_after_game"))
        self.assertNotContains(response, "Most read")
        self.assertContains(response, 'name="EMAIL"')

    def test_latest_is_empty_without_stories(self):
        with fetching(OSError("timed out"), OSError("timed out")):
            response = self.client.get(reverse("news_latest"))
        self.assertEqual(response.content.strip(), b"")

    def test_latest_mixes_new_and_deeply_read_stories(self):
        # The feed, the deeply-read list, then each deeply-read story's page
        # for its picture.
        with fetching(RSS, MOST_READ, ARTICLE, ARTICLE):
            response = self.client.get(reverse("news_latest"))
        self.assertContains(response, "Just published", count=2)
        self.assertContains(response, "Readers&#x27; pick", count=2)
        self.assertContains(response, "Newest story")
        self.assertContains(response, "Second story")
        self.assertContains(response, 'src="https://groundup.org.za/media/m.jpg"')

    def test_latest_does_not_repeat_a_story(self):
        rss = RSS.replace(b"https://groundup.org.za/article/new/", b"https://groundup.org.za/article/a/")
        with fetching(rss, MOST_READ, ARTICLE):
            response = self.client.get(reverse("news_latest"))
        self.assertContains(response, "article/a/", count=1)

    def test_top_is_the_most_read_story(self):
        with fetching(MOST_READ):
            response = self.client.get(reverse("news_top"))
        self.assertContains(response, "First story")
        self.assertNotContains(response, "Second story")

    def test_top_is_empty_without_stories(self):
        with fetching(OSError("timed out")):
            response = self.client.get(reverse("news_top"))
        self.assertEqual(response.content.strip(), b"")
