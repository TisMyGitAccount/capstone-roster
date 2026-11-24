from django import forms

from .importing import default_term
from .models import Student

MAX_UPLOAD_BYTES = 2 * 1024 * 1024


class RosterImportForm(forms.Form):
    file = forms.FileField(label="Roster CSV file")
    term = forms.CharField(
        max_length=10,
        initial=default_term,
        help_text=(
            "Only rows for this term are used. Rows with no term column "
            "are assumed to be for it."
        ),
    )
    mode = forms.ChoiceField(
        choices=[
            ("preview", "Preview only (nothing is changed)"),
            ("apply", "Apply to the roster"),
        ],
        widget=forms.RadioSelect,
        initial="preview",
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(".csv"):
            raise forms.ValidationError("Please upload a .csv file.")
        if upload.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError("That file is larger than 2 MB.")
        return upload

    def clean_term(self):
        return self.cleaned_data["term"].strip().upper()


class StatusOverrideForm(forms.Form):
    new_status = forms.ChoiceField(choices=Student.Status.choices, label="New status")
    reason = forms.CharField(
        label="Reason",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Saved in the audit log with your username.",
    )

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()
        if len(reason) < 10:
            raise forms.ValidationError(
                "Please give a reason of at least 10 characters so the audit "
                "log explains the change."
            )
        return reason