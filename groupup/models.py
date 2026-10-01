from django.db import models
from django.utils import timezone

from crossword.models import default_copyright

GROUPS = 4
WORDS = 4


class GroupUpQuerySet(models.QuerySet):
    def published(self):
        return self.filter(published__isnull=False, published__lte=timezone.now())


class GroupUp(models.Model):
    name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    authors = models.CharField(max_length=200, blank=True)
    editors = models.CharField(max_length=200, blank=True)
    copyright = models.CharField(max_length=200, default=default_copyright)
    groups = models.JSONField(default=list, blank=True)
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    published = models.DateTimeField(null=True, blank=True)

    objects = GroupUpQuerySet.as_manager()

    class Meta:
        verbose_name = "GroupUp"
        permissions = [("can_generate_groupups", "Can generate GroupUps")]

    def is_published(self):
        return self.published is not None and self.published <= timezone.now()

    def words(self):
        return [word for group in self.groups for word in group["words"] if word]

    def __str__(self):
        return self.name
