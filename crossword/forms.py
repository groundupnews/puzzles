from django import forms

from .models import Crossword


class CrosswordCreateForm(forms.ModelForm):
    """The "new crossword" form: just the grid size (a pseudo-field, not
    stored directly on the model). Saving expands the chosen size into
    num_rows/num_cols and a blank grid. requires_rotational_symmetry is left
    at its model default and is only ever changed later, on the edit
    screen."""

    SIZE_CHOICES = [
        (5, "5 x 5"),
        (7, "7 x 7"),
        (9, "9 x 9"),
        (15, "15 x 15"),
        (19, "19 x 19"),
    ]

    size = forms.TypedChoiceField(choices=SIZE_CHOICES, coerce=int, label="Grid size")

    class Meta:
        model = Crossword
        fields = []

    def save(self, commit=True):
        # `size` isn't a model field -- it's fanned out here into the
        # square num_rows/num_cols and a freshly blanked cells/
        # blocked_out_squares, which is what actually makes the new
        # Crossword a valid, empty grid ready for the edit screen.
        crossword = super().save(commit=False)
        size = self.cleaned_data["size"]
        crossword.num_rows = size
        crossword.num_cols = size
        crossword.cells = [""] * (size * size)
        crossword.blocked_out_squares = []
        if commit:
            crossword.save()
        return crossword
