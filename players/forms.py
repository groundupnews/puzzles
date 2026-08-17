from django import forms

from .models import Player


class PlayerProfileForm(forms.ModelForm):
    """Player's public profile: display_name lives on Player, but
    first_name/last_name are pseudo-fields that write through to the
    associated User. Email is deliberately not editable here: it's used
    to log in, so changing it must go through allauth's own flow rather
    than this form."""

    first_name = forms.CharField(max_length=150, required=False, help_text="Optional.")
    last_name = forms.CharField(max_length=150, required=False, help_text="Optional.")

    class Meta:
        model = Player
        fields = ["display_name"]
        help_texts = {
            "display_name": "This is the only name that will be shown publicly.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # display_name is blank=True on the model (so save() can fill in
        # its default outside a form, e.g. via the admin) but is required
        # whenever it's presented in this form.
        self.fields["display_name"].required = True
        user = self.instance.user
        self.initial["first_name"] = user.first_name
        self.initial["last_name"] = user.last_name
        if not self.instance.pk:
            self.initial["display_name"] = f"player_{user.pk}"

    def save(self, commit=True):
        player = super().save(commit=commit)
        user = player.user
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        if commit:
            user.save()
        return player
