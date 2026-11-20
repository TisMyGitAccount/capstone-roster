# capstone-roster

A standalone roster service that keeps a synced, verifiable copy of
enrolled students, keyed on a stable student ID rather than names.

**This project runs on simulated data.** It does not connect to
Panthersoft. A mock source adapter stands in for it, and a real adapter
can replace it later without changing the rest of the system.
See `docs/problem-statement.md` for the problem this addresses.

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

## Project layout

- `config/`  Django project settings
- `roster/`  Roster app (models, sync logic, API)
- `docs/`    Problem statement and design notes

## Status

Work in progress. Planned order: models, fake data, sync logic,
admin interface, read-only API.
