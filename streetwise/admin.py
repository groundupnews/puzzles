from django import forms
from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.html import format_html

from .models import Council, Streetwise, VotingDistrict, parse_street_view_link


@admin.register(VotingDistrict)
class VotingDistrictAdmin(admin.ModelAdmin):
    """Read-only: districts come from the IEC import."""

    list_display = ["number", "station", "municipality", "province", "winner"]
    list_filter = ["province"]
    search_fields = ["number", "station", "municipality"]
    readonly_fields = ["results"]
    exclude = ["votes"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    @admin.display(description="winner")
    def winner(self, obj):
        party, share = obj.winner()
        return f"{party} {share:.1f}%"

    def results(self, obj):
        return render_to_string("streetwise/results.html", {"district": obj})


@admin.register(Council)
class CouncilAdmin(admin.ModelAdmin):
    """Read-only: councils come from the IEC import."""

    list_display = ["code", "name", "year", "largest", "seats_won", "has_majority"]
    list_filter = ["year"]
    search_fields = ["code", "name"]
    readonly_fields = ["seats_by_party"]
    exclude = ["seats"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def largest(self, obj):
        return " and ".join(obj.largest())

    @admin.display(description="seats")
    def seats_won(self, obj):
        return f"{obj.most_seats()} of {obj.total()}"

    @admin.display(boolean=True, description="majority")
    def has_majority(self, obj):
        return obj.has_majority()

    def seats_by_party(self, obj):
        return ", ".join(f"{party} {seats}" for party, seats in obj.ranked())


class StreetwiseForm(forms.ModelForm):
    street_view_link = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"size": 100}),
        help_text="Find the spot in Google Maps, look the way players should "
        "start out looking, and paste the address bar here. It fills in the "
        "panorama and view below when you save.",
    )

    class Meta:
        model = Streetwise
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Coming from the link, these can be left empty on a new puzzle.
        for name in ["latitude", "longitude"]:
            self.fields[name].required = False

    def clean(self):
        data = super().clean()
        link = data.get("street_view_link")
        if link:
            try:
                data.update(parse_street_view_link(link))
            except ValueError as error:
                self.add_error("street_view_link", str(error))
        if data.get("latitude") is None or data.get("longitude") is None:
            self.add_error("street_view_link", "Paste a Street View link.")
        return data


@admin.register(Streetwise)
class StreetwiseAdmin(admin.ModelAdmin):
    form = StreetwiseForm
    list_display = ["pk", "number", "district", "published", "is_published", "rejected"]
    list_filter = ["rejected", "district__province"]
    search_fields = ["pk", "district__number", "district__station", "district__municipality"]
    autocomplete_fields = ["district"]
    readonly_fields = ["preview", "result", "number", "play"]
    fieldsets = [
        (None, {"fields": ["district", "street_view_link", "preview", "result"]}),
        ("View", {"fields": ["pano", "latitude", "longitude", "heading", "pitch", "fov"]}),
        ("Publishing", {"fields": ["published", "rejected", "notes", "number", "play"]}),
    ]

    class Media:
        css = {"all": ["streetwise/streetwise.css"]}

    def view_on_site(self, obj):
        # A plain path stays on whichever server the editor is on; the
        # default goes through the Sites framework's domain instead.
        return obj.get_absolute_url()

    @admin.display(boolean=True, description="published")
    def is_published(self, obj):
        return obj.is_published()

    def preview(self, obj):
        if not obj.pk:
            return "Save to see what players will see."
        return render_to_string("streetwise/panorama.html", {"puzzle": obj})

    def result(self, obj):
        if not obj.pk:
            return "-"
        return render_to_string("streetwise/results.html", {"district": obj.district, "puzzle": obj})

    def play(self, obj):
        if not obj.pk:
            return "-"
        return format_html('<a href="{}" target="_blank">Open it as a player</a>', obj.get_absolute_url())
