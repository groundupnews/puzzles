from django.contrib import admin

from .models import Target


@admin.register(Target)
class TargetAdmin(admin.ModelAdmin):
    list_display = ['pk', 'number', 'letters', 'published', 'is_published']
    search_fields = ['letters', 'pk']
    ordering = ['-modified']
