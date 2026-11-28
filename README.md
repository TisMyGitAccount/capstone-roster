# capstone-roster

A standalone roster service that keeps a synced, verifiable copy of
enrolled students, keyed on a stable student ID rather than names.

**This project runs on simulated data.** It does not connect to
Panthersoft. A mock source adapter stands in for it, and a real adapter
can replace it later without changing the rest of the system.
See `docs/problem-statement.md` for the problem this addresses.

## Documentation

- `docs/problem-statement.md`: the problem this project addresses
- `docs/identity-rules.md`: the identity rules, and the test that proves each one
- `docs/csv_import.md`: loading roster data from an exported file
- `docs/admin-tools.md`: the sync banner, same-name flag, and status override
- `docs/permissions-and-data-privacy.md`: permissions and data privacy rules for roster data and discrepancies
- `docs/api.md`: the read-only API
- `docs/limitations.md`: known limits and next steps

## Setup (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Edit `.env` and set `DJANGO_SECRET_KEY`. Generate one with:

```
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Then open http://127.0.0.1:8000/admin

## Run the demo

```
python manage.py generate_demo_data
python manage.py sync_roster --snapshot snapshot_1.json --reset
python manage.py sync_roster --snapshot snapshot_2.json
python manage.py sync_roster --snapshot snapshot_dirty.json
python manage.py sync_roster --snapshot snapshot_3_mass_drop.json
python manage.py sync_roster --snapshot fail
```

Each command simulates a different Panthersoft export: the initial roster,
a later one with drops and new enrollments, one with messy records, one that
would deactivate too many students (blocked), and an outage. Results appear
in the admin under *Students*, *Sync logs*, *Sync issues*, and
*Roster audits*.

## Presentation walkthrough

Setup (before presenting):

```
python manage.py make_sample_csv
python manage.py sync_roster --snapshot snapshot_1.json --reset
python manage.py create_api_token --name capstone-site --replace
python manage.py runserver
```

Copy the token it prints (shown once). Log in to http://127.0.0.1:8000/admin.
The roster now holds the first export: 300 students.

1. **Identity is the ID, not the name.** In *Students*, filter by *same name*.
   Several pairs share a name but have different IDs, and the list flags them.
2. **A student the source still lists is accepted.** In a browser, open
   `/api/roster/students/9000001/`. Danielle Johnson is `active` and `eligible`.
3. **Import a new export.** *Students > Import roster file*, choose
   `roster/demo_data/csv/snapshot_2_export_style.csv`, leave **Preview only**,
   and run. Point out the list: 13 added, 7 updated (with old and new values),
   8 deactivated. Nothing has changed yet. Upload again with **Apply**.
4. **The same student is now refused, with a reason.** Reload
   `/api/roster/students/9000001/`: `eligible` is false, `inactive`, and the
   reason says when she was last confirmed. Open `/api/roster/students/9000035/`
   (Leslie Adams) for the accepted case.
5. **Bad records are set aside, not guessed at.** Import
   `snapshot_dirty.csv`. Nothing changes, and 8 records are listed with the
   reason each was refused (letters in an ID, a partial ID, a blank ID, a
   duplicate ID, an email claimed by someone else).
6. **A bad export can't wipe the roster.** Import `snapshot_3_mass_drop.csv`.
   It is blocked because it would deactivate 45% of students. The banner on
   *Students* turns yellow.
7. **A broken file is refused.** Import `bad_missing_email.csv`. It fails with
   a message naming the missing column, and nothing changes.
8. **Overrides need a reason.** Select a student, choose *Change status (a
   reason is required)*. A blank reason is refused. Then open *Roster audits*
   to show who changed what and why.
9. **Other sites can ask.** In a second terminal, create a token and call the API:

```
python manage.py create_api_token --name capstone-site --replace
$h = @{ Authorization = "Bearer PASTE_TOKEN_HERE" }
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/roster/students/9000035/ -Headers $h
```

   Then log out of the admin and open the same address in the browser to
   show the `401`. The PowerShell call still works, because the token does
   not depend on a browser login.

To rerun the demo, repeat the setup commands. The `--reset` flag clears the
roster back to the first export.

## Tests

```
python manage.py test
```

## Project layout

- `config/`  Django project settings
- `roster/`  Roster app (models, sync logic, identity rules, CSV import, admin, API)
- `docs/`    Problem statement, identity rules, CSV import, admin tools, permissions and data privacy, and API documentation

## Status

Working: roster models, identity rules, CSV import with preview, sync with
safeguards, admin banner, same-name flag, audited status override, permissions
and data privacy safeguards, read-only API with token authentication, and automated tests.

Not built: a connection to the real Panthersoft (the project runs on
simulated data), SSO login, and scheduled syncing.