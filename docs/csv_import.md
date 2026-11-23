# CSV import

Admins load roster data by uploading an export in the admin: **Students >
Import roster file**. The same rules and safeguards apply as for any source
(see `identity-rules.md`).

## The file

- **Required columns:** student ID, first name, last name, email. Header names
  are matched flexibly (`Student ID`, `ID`, `EMPLID`, `First Name`, `Email Address`,
  and similar). Extra columns are ignored.
- **Optional column:** `term`. Rows with no term use the term chosen on the
  form. Only rows for that term are imported.
- **Encoding:** UTF-8. From Excel, use *Save As > CSV UTF-8*. Other encodings
  are refused rather than guessed.
- **Delimiter:** comma, semicolon, or tab, detected from the header row.
- **Limits:** 2 MB and 20,000 rows. Blank lines are skipped.

## Student IDs and spreadsheets

IDs are 7 digits. Spreadsheets sometimes damage them: dropping leading zeros
or turning `9000001` into `9000001.0`. The roster does not repair or guess.
Those rows are **set aside** as invalid and listed with the reason. If more
than 10% of rows are unusable, the whole file is refused.

## Workflow

1. Choose the file and leave **Preview only** selected. Nothing is changed;
   the page shows exactly who would be added, updated, or deactivated, and
   which rows would be set aside.
2. If it looks right, upload the same file again and choose **Apply**.

A file that would deactivate more than 10% of active students is blocked for
review, and any error leaves the roster untouched.

## What is recorded

The sync log records the file name and who ran it, and each change is in the
audit log under that admin's username. The file itself is not stored. Real
exports must never be committed to the repository (the `.gitignore` blocks
`.csv` files outside the fake demo folder).

## From the command line

    python manage.py import_roster_csv path\to\export.csv --term FA26
    python manage.py import_roster_csv path\to\export.csv --term FA26 --apply