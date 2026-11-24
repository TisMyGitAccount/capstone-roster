# Limitations and next steps

This is a basic roster system that can be built on. It runs on simulated data
and is not ready for production. Each limit below says why it exists and what
the next step would be.

## Data source

| Limit | Why | Next step |
|---|---|---|
| **No connection to Panthersoft.** All data is simulated (fake names, IDs in the 9,000,000 range, `example.edu` emails). | The source could not be reached or imported from, and the site's maintainers did not respond. | Write a real adapter with `fetch_enrolled(term)` (database view, API, or file drop). Nothing else changes, because every source passes through the same rules. |
| **Roster loads by manual CSV upload**, not on a schedule. | A real export is the only input available without access to the source. | Schedule the import once an adapter exists. Until then, staleness is visible: every API response carries a freshness flag and the admin banner turns yellow after 24 hours. |
| **The real export format is unknown.** Header names are matched flexibly, but a different layout could be refused. | No real export was available to test against. | Send the refused file's column names and add them as aliases. The error message lists the columns it found. |
| **ID format is assumed:** 7 digits, no letters. | Taken from the project's own rules, not checked against real Panthersoft IDs. | Confirm the real format and set `ROSTER_ID_LENGTH`. |

## Identity

| Limit | Why | Next step |
|---|---|---|
| **Conflicts are detected on email only.** | Email is the only secondary identity field the roster stores. | Add other fields the source provides, such as a second stable identifier. |
| **Fallback matching uses names only and never merges.** A record with no ID is set aside with suggested matches. | No date of birth is stored, deliberately, to avoid holding sensitive data. Name matching is the problem this project exists to avoid. | Keep it as suggestions for an administrator. |
| **Students entered by hand** in the admin are checked for digits only, not length. | The length and whitespace rules run during import. | Apply the same checks to manual entry. |

## Access

| Limit | Why | Next step |
|---|---|---|
| **No student login (SSO).** API tokens identify the calling site, not the student. | FIU's login system was not available. | The calling site still logs its own users in. SSO would let the roster confirm who is at the keyboard, and can be added without changing the endpoints. |
| **Tokens never expire** and the API has no rate limiting. | Kept simple for a demo. | Add expiry and rate limits. |
| **Only staff can use the admin**, and there are no roles such as advisor or instructor. | Out of scope for a basic roster. | Add roles and team assignment. |

## Admin workflow

| Limit | Why | Next step |
|---|---|---|
| **A blocked import cannot be approved from the admin.** If a legitimate import drops more than 10% (for example after the add/drop deadline), the only way through is changing a setting. | The threshold was built as a hard stop first. | Add an audited "approve this blocked import" action that requires a reason. |
| **Overrides can be reversed by the next import**, because the source is the authority. | By design: a roster that disagrees with the source is the original problem. Both the override and the reversal are in the audit log. | If overrides need to persist, record them separately as exceptions that an administrator reviews. |
| **The current term is a setting** (`ROSTER_CURRENT_TERM`), changed by hand. | Simple for one term. | Derive it from the calendar or the source. |
| **Students cannot resolve problems themselves.** The roster now tells them why they are refused, but fixing it still goes through an administrator. | Fixing enrollment is outside this system. | Notify students when their status changes and link to the right office. |

## Not production-ready

- Runs on Django's development server and SQLite, without HTTPS.
- Secrets come from a `.env` file, and `DEBUG` should be `False` anywhere real. The demo key used during development was committed to the public history and must never be reused.
- Tested for hundreds of students. Larger rosters are not measured.
- The audit log is protected in the admin but not against someone with direct database access.

## What was tested

98 automated tests cover each identity rule, the sync safeguards, the CSV
import, the API, and the admin features (`python manage.py test`). The admin
pages were checked by hand, and there are no automated browser tests.