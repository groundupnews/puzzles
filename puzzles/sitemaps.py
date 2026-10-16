from django.contrib.sitemaps import Sitemap
from django.contrib.sites.requests import RequestSite
from django.shortcuts import render
from django.urls import reverse

from crossword.models import Crossword
from groupup.models import GroupUp
from quizzes.models import Quiz
from streetwise.models import Streetwise
from sudoku.models import Sudoku
from target.models import Target


class PagesSitemap(Sitemap):
    def items(self):
        return [
            "home",
            "crossword_select",
            "quiz_select",
            "sudoku:list",
            "target:list",
            "groupup:list",
            "streetwise:list",
        ]

    def location(self, item):
        return reverse(item)


class PuzzleSitemap(Sitemap):
    def __init__(self, model, date_field):
        self.model = model
        self.date_field = date_field

    def items(self):
        return self.model.objects.published().order_by("pk")

    def lastmod(self, puzzle):
        return getattr(puzzle, self.date_field)


SITEMAPS = [
    PagesSitemap(),
    PuzzleSitemap(Crossword, "date_modified"),
    PuzzleSitemap(Quiz, "date_modified"),
    PuzzleSitemap(Sudoku, "modified"),
    PuzzleSitemap(Target, "modified"),
    PuzzleSitemap(GroupUp, "date_modified"),
    PuzzleSitemap(Streetwise, "modified"),
]


def sitemap(request):
    """Takes the domain from the request, not the Sites framework."""
    site = RequestSite(request)
    urls = [
        url
        for section in SITEMAPS
        for url in section.get_urls(site=site, protocol=request.scheme)
    ]
    return render(request, "sitemap.xml", {"urlset": urls}, content_type="application/xml")
