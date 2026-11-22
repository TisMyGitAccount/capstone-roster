# Roster API

A read-only HTTP API for checking whether a student is on the roster.
It runs on simulated data in this project; the same endpoints apply when a
real source is connected.

Base path: `/api/roster/`

## Authentication

Every request needs a token. Anonymous requests get `401`.

Send it in the `Authorization` header:

    Authorization: Bearer <token>

Create a token (one per consuming site):

    python manage.py create_api_token --name capstone-site

The token is **shown once** and only a hash is stored, so copy it
immediately. Revoke a token in the admin under *Api tokens* by unticking
*Is active*; its next request returns `401`.

A logged-in staff user in the admin can also read the API from a browser,
which is handy for testing.

A token identifies the **calling site**, not the student. The calling site
must log its own users in and ask about the ID that login produced. The
roster can say whether an ID is enrolled, but it cannot prove who is at the
keyboard.

Never commit a real token to the repository.

## Endpoints

All endpoints are `GET` only. Other methods return `405`.

### `GET /api/roster/students/<id>/`

Is this ID on the active roster, and if not, why not?

The ID is trimmed of surrounding whitespace before lookup, using the same
rules as the sync. IDs are 7 digits (`ROSTER_ID_LENGTH`).

Active student:

```json
{
  "queried_id": "9000035",
  "eligible": true,
  "current_term": "FA26",
  "warning": null,
  "data_freshness": {
    "last_successful_sync_at": "2026-11-22T17:52:39Z",
    "age_hours": 0.23,
    "stale": false,
    "stale_after_hours": 24
  },
  "status": "active",
  "reason": "Active on the FA26 roster.",
  "student": {
    "panthersoft_id": "9000035",
    "first_name": "Leslie",
    "last_name": "Adams",
    "email": "leslie.adams.35@example.edu",
    "term": "FA26",
    "status": "active",
    "last_synced_at": "2026-11-22T17:52:39.891005Z"
  }
}
```

Student no longer enrolled (same shape, with `"eligible": false`,
`"status": "inactive"`, and a reason such as
`"Not enrolled according to the latest sync. Last confirmed enrolled: 2026-11-22 17:52 UTC."`).

| HTTP | `status` | Meaning |
|---|---|---|
| 200 | `active` | On the roster. `eligible` is true only if the student's term is the current term. |
| 200 | `inactive` | Was on the roster, absent from the latest sync. `eligible` is false. |
| 200 | `pending_review` | Held for an administrator. `eligible` is false. |
| 400 | `invalid_id` | The ID is malformed (letters, symbols, wrong length, blank). This is a problem with the ID that was sent, **not** evidence the student is missing. No `student` field. |
| 404 | `not_found` | A well-formed ID that is not on the roster. No `student` field. |

Partial IDs never match: `90001` returns `invalid_id`, not the student whose
ID starts with those digits.

### `GET /api/roster/students/`

The roster for a term, paginated.

| Parameter | Default | Notes |
|---|---|---|
| `term` | current term | For example `FA26` |
| `status` | all | `active`, `inactive`, or `pending_review`. Anything else returns `400`. |
| `page` | 1 | |
| `page_size` | 50 | Maximum 200 |

Response fields: `count`, `next`, `previous`, `results` (a list of students),
`current_term`, and `data_freshness`. Results are sorted by last name, first
name, then ID.

### `GET /api/roster/status/`

Is the roster fresh, and how did the latest sync go?

```json
{
  "current_term": "FA26",
  "data_freshness": { "last_successful_sync_at": "...", "age_hours": 0.2, "stale": false, "stale_after_hours": 24 },
  "latest_sync": {
    "status": "success",
    "started_at": "...",
    "finished_at": "...",
    "added": 13,
    "updated": 7,
    "deactivated": 8,
    "set_aside_records": 0,
    "message": ""
  },
  "students_in_current_term": { "active": 305, "inactive": 8, "pending_review": 0 }
}
```

`latest_sync.status` is `success`, `partial` (blocked for review, nothing
applied), or `failed` (nothing applied). `message` explains a blocked or
failed sync.

## Data freshness

Every response includes `data_freshness`, based on the **last successful
sync**. If it is older than `ROSTER_STALE_AFTER_HOURS` (24 by default), or
the roster has never synced, then `stale` is `true` and the lookup response
carries a `warning` in plain language.

Stale data is flagged, not refused: the lookup still answers, and the calling
site decides how to present it.

## Errors

| HTTP | Cause |
|---|---|
| 400 | Malformed ID or invalid filter value |
| 401 | Missing, wrong, or revoked token |
| 403 | Logged-in user who is not staff |
| 404 | Well-formed ID not on the roster |
| 405 | Any method other than `GET` |

## Examples

PowerShell:

    $h = @{ Authorization = "Bearer PASTE_TOKEN_HERE" }
    Invoke-RestMethod -Uri http://127.0.0.1:8000/api/roster/students/9000035/ -Headers $h

curl:

    curl -H "Authorization: Bearer PASTE_TOKEN_HERE" http://127.0.0.1:8000/api/roster/students/9000035/

Add `?format=json` to a URL to get plain JSON in a browser.

## Settings

| Setting | Default | Purpose |
|---|---|---|
| `ROSTER_CURRENT_TERM` | `FA26` | Term used for eligibility and default listings |
| `ROSTER_STALE_AFTER_HOURS` | `24` | Age at which data is flagged stale |
| `ROSTER_ID_LENGTH` | `7` | Required ID length |