from django import forms
from django.core.exceptions import ValidationError

from .models import GROUPS, WORDS, GroupUp


class GroupUpForm(forms.ModelForm):
    class Meta:
        model = GroupUp
        fields = ["name", "authors", "editors", "copyright", "description", "published"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "published": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        saved = self.instance.groups
        for g in range(GROUPS):
            group = saved[g] if g < len(saved) else {"label": "", "words": [""] * WORDS}
            self.fields[f"label_{g}"] = forms.CharField(
                required=False,
                max_length=200,
                initial=group["label"],
                widget=forms.TextInput(
                    attrs={"placeholder": "What links them", "aria-label": f"Group {g + 1} connection"}
                ),
            )
            for w in range(WORDS):
                self.fields[f"word_{g}_{w}"] = forms.CharField(
                    required=False,
                    max_length=100,
                    initial=group["words"][w],
                    widget=forms.TextInput(
                        attrs={"placeholder": "Word", "aria-label": f"Group {g + 1} word {w + 1}"}
                    ),
                )

    @classmethod
    def from_json(cls, puzzle):
        groups = puzzle.get("groups") if isinstance(puzzle, dict) else None
        if not (
            isinstance(groups, list)
            and len(groups) == GROUPS
            and all(
                isinstance(group, dict)
                and isinstance(group.get("words"), list)
                and len(group["words"]) == WORDS
                for group in groups
            )
        ):
            raise ValueError(
                f'needs "groups": a list of {GROUPS} groups, each with a "label" and {WORDS} "words".'
            )
        instance = GroupUp()
        data = {"copyright": instance.copyright}
        data.update({name: puzzle[name] or "" for name in cls._meta.fields if name in puzzle})
        for g, group in enumerate(groups):
            data[f"label_{g}"] = group.get("label") or ""
            for w, word in enumerate(group["words"]):
                data[f"word_{g}_{w}"] = word or ""
        return cls(data, instance=instance)

    def error_list(self):
        return [
            message if field == "__all__" else f"{self[field].label or field}: {message}"
            for field, messages in self.errors.items()
            for message in messages
        ]

    def meta(self):
        return [self[name] for name in self._meta.fields]

    def groups(self):
        return [
            (self[f"label_{g}"], [self[f"word_{g}_{w}"] for w in range(WORDS)])
            for g in range(GROUPS)
        ]

    def clean(self):
        cleaned = super().clean()
        self.cleaned_groups = [
            {
                "label": cleaned.get(f"label_{g}", ""),
                "words": [cleaned.get(f"word_{g}_{w}", "") for w in range(WORDS)],
            }
            for g in range(GROUPS)
        ]
        words = [w for group in self.cleaned_groups for w in group["words"] if w]
        seen = set()
        for word in words:
            if word.casefold() in seen:
                raise ValidationError(f"{word} is used more than once. Every word must be different.")
            seen.add(word.casefold())
        complete = len(words) == GROUPS * WORDS and all(g["label"] for g in self.cleaned_groups)
        if cleaned.get("published") and not complete:
            raise ValidationError(
                "Fill in every connection and all sixteen words before setting a publication date."
            )
        return cleaned

    def save(self, commit=True):
        self.instance.groups = self.cleaned_groups
        return super().save(commit)
