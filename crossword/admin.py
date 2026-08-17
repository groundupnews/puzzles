from allauth.account.admin import EmailConfirmationAdmin
from allauth.account.models import EmailConfirmation
from django.contrib import admin

from .models import Clue, Crossword, Entry, Word

# allauth registers EmailAddress itself, but skips EmailConfirmation
# whenever EMAIL_CONFIRMATION_HMAC is on (the default here) since
# confirmations are then verified from a signed token rather than a
# stored row. Registered anyway for visibility; expect it to stay empty
# unless that setting is turned off.
admin.site.register(EmailConfirmation, EmailConfirmationAdmin)


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    """Lets a staff user flip exclude_from_recommendations right from the
    list view (list_editable) instead of opening each Word individually --
    that flag is the main reason anyone would visit this admin page."""

    list_display = ("text", "exclude_from_recommendations", "date_added", "date_modified")
    list_editable = ("exclude_from_recommendations",)
    list_filter = ("exclude_from_recommendations",)
    search_fields = ("text",)
    ordering = ("text",)


@admin.register(Clue)
class ClueAdmin(admin.ModelAdmin):
    """list_select_related avoids one extra query per row for `text__text`
    (the linked Word) when rendering the change list."""

    list_display = ("text", "clue", "date_added", "date_modified")
    search_fields = ("text__text", "clue")
    list_select_related = ("text",)


@admin.register(Crossword)
class CrosswordAdmin(admin.ModelAdmin):
    """date_added/date_modified are auto-set fields (see models.py) so
    they're read-only here rather than editable. view_on_site uses
    Crossword.get_absolute_url() to link straight to the public solver."""

    list_display = (
        "__str__",
        "num_rows",
        "num_cols",
        "published",
        "date_modified",
    )
    search_fields = ("name", "description")
    readonly_fields = ("date_added", "date_modified")
    view_on_site = True


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    """list_select_related avoids one query per row for each of the three
    foreign keys shown in list_display (crossword, word, clue)."""

    list_display = ("crossword", "number", "direction", "word", "clue")
    list_filter = ("direction",)
    search_fields = ("word__text",)
    list_select_related = ("crossword", "word", "clue")
