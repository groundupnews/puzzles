from django import forms

from .models import Player


class PlayerProfileForm(forms.ModelForm):
    """Player's public profile: display_name lives on Player, but
    first_name/last_name/email are pseudo-fields that write through to
    the associated User."""

    first_name = forms.CharField(max_length=150, required=False, help_text="Optional.")
    last_name = forms.CharField(max_length=150, required=False, help_text="Optional.")
    email_address = forms.EmailField(
        label="Email address",
        help_text="Used to contact you and log in. Never shown publicly.",
    )

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
        self.initial["email_address"] = user.email
        if not self.instance.pk:
            self.initial["display_name"] = f"player_{user.pk}"

    def save(self, commit=True):
        player = super().save(commit=commit)
        user = player.user
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email_address"]
        if commit:
            user.save()
        return player
