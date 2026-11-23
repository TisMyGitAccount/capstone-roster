# capstone-roster

A standalone roster service that keeps a synced, verifiable copy of
enrolled students, keyed on a stable student ID rather than names.

**This project runs on simulated data.** It does not connect to
Panthersoft. A mock source adapter stands in for it, and a real adapter
can replace it later without changing the rest of the system.
See `docs/problem-statement.md` for the problem this addresses.

The identity rules, and the test that proves each one, are in
`docs/identity-rules.md`.

The read-only API is documented in `docs/api.md`.

The CSV import is described in `docs/csv-import.md`.

## Setup (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
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

## Tests

```
python manage.py test
```

## Project layout

- `config/`  Django project settings
- `roster/`  Roster app (models, sync logic, identity rules, API)
- `docs/`    Problem statement, identity rules, and API documentation

## Status

Working: roster models, identity rules, sync from a simulated source with
safeguards, admin interface, read-only API with token authentication, and
automated tests.

Planned: "Sync now" admin action, last-sync banner, duplicate-name flag, and
manual override with a required reason.