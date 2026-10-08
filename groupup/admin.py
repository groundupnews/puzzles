from django.contrib import admin

from .models import GroupUp


@admin.register(GroupUp)
class GroupUpAdmin(admin.ModelAdmin):
    list_display = ["pk", "name", "authors", "published", "is_published"]
    search_fields = ["name", "authors", "pk"]
    ordering = ["-date_modified"]
    readonly_fields = ["date_added", "date_modified"]

    @admin.display(boolean=True)
    def is_published(self, obj):
        return obj.is_published()
