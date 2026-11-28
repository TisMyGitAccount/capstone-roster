# Permissions and Data Privacy

Rules and boundaries for viewing, managing, and consuming student roster data
and identity discrepancies.

This document fulfills **User Story 1 (US1): Permissions and Data Privacy
Documentation** for the Capstone Roster project (*"A Roster the Capstone Site
Can Trust"*).

---

## 1. Overview and Slice Boundary

The Capstone ecosystem operates under a formal slice agreement between
**Team A** and **Team B**:

- **Team A (Capstone Roster)** owns roster reconciliation end-to-end:
  ingestion, normalization, matching, identity resolution, exception handling,
  duplicate and missing-record detection, and maintaining the traceable roster
  record.
- **Team B (Capstone Assist)** owns AI-assisted support and ticketing workflows
  end-to-end. Team B consumes agreed roster information from Team A as
  **read-only context**, solely when needed to associate a support interaction
  or ticket with the correct verified Capstone user.

This document establishes the permissions architecture, role-based access
controls, and data privacy policies governing Team A's roster system, with
particular emphasis on how student records and **quarantined identity
discrepancies** are accessed, audited, and protected.

---

## 2. Student Data Privacy and FERPA Compliance

Student educational records are protected under the **Family Educational
Rights and Privacy Act (FERPA)** (34 CFR Part 99). The roster service enforces
privacy by design through strict data minimization and architectural separation.

### 2.1 Data Minimization Principle

The roster stores only the minimum attributes necessary to establish student
identity and verify active enrollment for the current term:

| Attribute | Privacy Classification | Purpose |
|---|---|---|
| `panthersoft_id` | Institutional Identifier | Stable primary key (7 numeric digits). Names are display-only and never used to establish identity. |
| `first_name` | Directory Information | Display only; fallback candidate matching suggestion (ID-07). |
| `last_name` | Directory Information | Display only; fallback candidate matching suggestion (ID-07). |
| `email` | Institutional Contact | Secondary identity validation to detect conflicts (Rule ID-14). |
| `term` | Academic Context | Restricts eligibility to the current active semester (e.g., `FA26`). |
| `status` | Operational State | `active`, `inactive`, or `pending_review`. |
| `last_synced_at` | Metadata | Verifies record freshness against the source. |

### 2.2 Prohibited and Excluded PII

To eliminate exposure risks, the following data elements are **strictly
prohibited** from ingestion, persistence, and API exposure:

1. **Social Security Numbers (SSN)**: Never accepted or stored.
2. **Date of Birth (DOB)**: Deliberately excluded. Under Rule ID-07 to ID-09,
   fallback candidate matching operates on normalized names as non-binding
   suggestions only, specifically avoiding the collection of birth dates.
3. **Financial and Financial Aid Records**: Excluded.
4. **Grades, GPA, and Academic Disciplinary Records**: Excluded.
5. **Physical Addresses and Personal Phone Numbers**: Excluded.
6. **Government Identifiers or Passports**: Excluded.

### 2.3 Secondary Identifier Privacy (Email)

Email addresses are restricted to institutional addresses (`@example.edu` or
`@fiu.edu`). Email is utilized exclusively to detect identity conflicts
(Rule ID-14: two source records sharing an email or a source record attempting
to claim an email registered to another student ID). Emails are never exposed
publicly and are never accessible to unauthenticated callers.

### 2.4 Synthetic Data Policy in Version Control

To comply with privacy laws, **no real student data is ever committed to
version control**. All demo snapshots (`snapshot_1.json`,
`snapshot_2.csv`, `snapshot_dirty.csv`, etc.) contain generated fake names,
synthetic 7-digit IDs in the `9,000,000` range, and `@example.edu` domain
addresses. Production connectors must connect directly to authorized database
views or secure drops without checking data into source repositories.

---

## 3. Permissions Architecture and Role Matrix

Access to the roster system is divided into five distinct operational roles.
Permissions follow the principle of least privilege.

### 3.1 Role Definitions

1. **System Administrator (Superuser)**
   - Responsible for deployment configuration, secret key management, and
     issuing/revoking machine API tokens (`ApiToken`).
   - Access to Django administrative interface.
2. **Roster Administrator (Staff / Registrar Liaison)**
   - Responsible for executing scheduled or manual CSV roster imports,
     reviewing sync banners, and investigating quarantined sync issues.
   - Authorized to perform audited status overrides with a mandatory written
     justification.
3. **Auditor / Read-Only Staff**
   - Authorized to inspect roster lists, audit trails (`RosterAudit`), and sync
     logs (`SyncLog`) without modification privileges.
4. **Consuming Client (Team B / Capstone Assist)**
   - Automated client querying the read-only REST API with a pre-shared Bearer
     token (`ApiTokenAuthentication`).
   - Scoped strictly to student lookup and data freshness checks. Has no
     access to administrative endpoints, discrepancy details, or audit logs.
5. **End User (Student / Public)**
   - No direct access to the roster service or API.
   - Students interact only with consuming frontends (Capstone Assist), which
     query the roster service on their behalf and communicate eligibility
     without leaking internal roster metadata.

### 3.2 Access Control Matrix

| System Resource / Action | System Admin | Roster Admin (Staff) | Auditor (Staff) | Team B API Token | Public / Student |
|---|:---:|:---:|:---:|:---:|:---:|
| **View Active Student List** | Yes | Yes | Yes | Paginated API | No (401) |
| **Search Student by ID** | Yes | Yes | Yes | Lookup API | No (401) |
| **View Same-Name Flags** | Yes | Yes | Yes | No | No (401) |
| **Perform Status Override** | Yes | Yes (Audited) | No | No (405) | No (401) |
| **Upload CSV Roster** | Yes | Yes | No | No (405) | No (401) |
| **View Sync Logs (`SyncLog`)** | Yes | Yes | Yes | Count / Status only | No (401) |
| **View Sync Issues (`SyncIssue`)** | Yes | Yes | Yes | No | No (401) |
| **Edit/Delete Sync Issues** | **No (Immutable)** | **No (Immutable)** | **No (Immutable)** | No | No |
| **View Audit Trail (`RosterAudit`)** | Yes | Yes | Yes | No | No (401) |
| **Edit/Delete Audit Entries** | **No (Immutable)** | **No (Immutable)** | **No (Immutable)** | No | No |
| **Create / Revoke API Tokens** | Yes | Revoke only | No | No | No |

---

## 4. Rules for Managing Roster Data and Overrides

### 4.1 Source Authority Principle

The upstream source (Panthersoft) is the sole authority for enrollment status.
Manual database edits cannot supersede the source.

- If a roster administrator overrides a student from `inactive` to `active`,
  the change is recorded in `RosterAudit`. However, if the subsequent sync
  still omits that student, the reconciliation engine automatically
  deactivates them again, preventing phantom enrollments.
- Students cannot be deleted in the admin interface (`has_delete_permission = False`).
  Dropping a student from enrollment marks them `inactive`, preserving historical
  traceability and preventing orphaned foreign keys in consuming services.

### 4.2 Mandatory Justification for Status Overrides

Status overrides bypass automated sync rules and therefore require accountability:
- Overrides must be submitted with a reason containing **at least 10 characters**.
- Overrides are recorded in `RosterAudit` with the authenticated administrator's
  username, timestamp, previous status, new status, and the stated reason.
- Blank or trivial reasons (e.g. "fix", "test") are rejected by form validation.

### 4.3 Safeguards on Manual Student Entry

If an administrator creates a student record manually in the administrative
interface:
- The system writes an audit entry flagging `manual_entry: True`.
- The administrator receives an immediate warning: *"Entered by hand. The next
  import will deactivate this student unless the source lists them."*
- Input validation ensures student IDs contain digits only (`RegexValidator`).

---

## 5. Rules for Managing Identity Discrepancies (`SyncIssue`)

When an incoming source record violates identity rules (Rule ID-01 through ID-16),
the reconciliation engine does **not** abort the entire sync. Instead, it
quarantines the offending record into a `SyncIssue` entry.

### 5.1 Quarantined Discrepancy Categories

| Discrepancy Kind | Triggering Rule | Data Stored in Quarantine | Privacy & Resolution Rule |
|---|---|---|---|
| `invalid_id` | ID-05, ID-06, ID-16 | Raw ID, invalid reason | Set aside. Upstream source must correct malformed identifier. |
| `missing_id` | ID-01, ID-07..09 | Raw record, suggested candidate IDs | Fallback suggestions are suggestions only. Never auto-merged. |
| `ambiguous` | ID-10, ID-15 | Raw record, multiple matching candidate IDs | No candidate selected. Administrator reviews with registrar. |
| `duplicate` | ID-11 | Raw records, count of duplicate occurrences | Neither copy applied; both quarantined to avoid arbitrary selection. |
| `conflict` | ID-14 | Conflicting email, conflicting roster IDs | Quarantined. Prevents account takeover or cross-student collision. |
| `invalid_record` | Missing required fields | Raw record, list of missing fields | Incomplete record quarantined without corrupting student table. |

### 5.2 Immutability of Discrepancies and Audit Records

Quarantined discrepancies are legal and technical evidence of data divergence
between Panthersoft and the Capstone platform. To maintain tamper-evident integrity:

1. **No Manual Creation (`has_add_permission = False`)**: Discrepancies can
   only be created by the automated classification engine in `sync.py`.
2. **No Manual Modification (`has_change_permission = False`)**: Discrepancy
   records are read-only. Administrators cannot edit quarantined payloads.
3. **No Deletion (`has_delete_permission = False`)**: Discrepancies cannot be
   purged through the UI. They remain linked to their parent `SyncLog`.
4. **Read-Only Fields**: All detail fields (`sync_log`, `kind`, `identifier`,
   `record`, `details`, `created_at`) are locked against modification.

### 5.3 Privacy Protection for Quarantined Records

Quarantined records in `SyncIssue` contain raw payload snippets from import
files. Access to the *Sync issues* view is restricted exclusively to
authenticated staff members (`is_staff = True`). Discrepancies are completely
excluded from the external API consumed by Team B.

---

## 6. Team A / Team B Consuming Service Boundaries

The slice agreement requires clean isolation between Team A's internal roster
state and Team B's support bot.

### 6.1 Cryptographic Token Authentication

Consuming services authenticate using HTTP Bearer tokens:
```
Authorization: Bearer <token>
```
- Tokens are generated via `python manage.py create_api_token --name <client-name>`.
- The raw secret is displayed **once** in the terminal upon generation.
- The database stores only a **SHA-256 cryptographic hash** (`key_hash`) along
  with an 8-character prefix for identification (`ApiToken`).
- Even with full database read access, a compromised database does not reveal
  valid API keys.
- Revocation is instant: setting `is_active = False` immediately invalidates
  subsequent requests without requiring server restart.

### 6.2 Read-Only Scope and Information Hiding

The API exposed to Team B (`/api/roster/*`) is strictly read-only (`GET` only):
- Non-GET requests return `405 Method Not Allowed`.
- Responses return student eligibility, active term, and verification
  timestamps.
- **Information Hiding**: The API never exposes internal audit history,
  administrator notes, manual override reasons, or quarantined sync issues.
- If a student is ineligible or pending review, the API reports the high-level
  reason (e.g., `"Not enrolled according to the latest sync"`) without leaking
  sensitive administrative annotations.

### 6.3 Staleness Visibility

Every API response carries a `data_freshness` block indicating the age of the
last successful sync and whether data is stale (`> 24 hours`). This allows
Team B's application to alert end users gracefully if roster data is out of
date, without requiring access to Team A's backend sync logs.

---

## 7. Verification and Automated Testing

Permissions and data privacy safeguards are verified by automated tests:

| Test Class | Focus Area | File |
|---|---|---|
| `DiscrepancyAndLogAdminPermissionTests` | Verifies `SyncIssue` and `SyncLog` cannot be created, edited, or deleted in admin. | `roster/test_admin_features.py` |
| `StudentAdminSafetyTests` | Verifies student forms are read-only, cannot be deleted, and manual additions trigger audit warnings. | `roster/test_admin_features.py` |
| `AuditAdminTests` | Verifies `RosterAudit` log is immutable and cannot be created, edited, or deleted in admin. | `roster/test_admin_features.py` |
| `ApiAuthTests` | Verifies Bearer token authentication, SHA-256 token hashing, token revocation, and rejection of non-staff sessions. | `roster/test_api.py` |
| `IdentityRuleTests` | Verifies identity rules ID-01 through ID-16, ensuring bad records are quarantined rather than misidentified. | `roster/tests.py` |

To run the permission and privacy test suite:

```bash
python manage.py test roster.test_admin_features
python manage.py test roster.test_api.ApiAuthTests
```
