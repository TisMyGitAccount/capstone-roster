# Admin tools

## Last-sync banner

The top of **Students** shows when the roster was last confirmed, from which
file, and the counts for the current term. It turns yellow when the data is
older than 24 hours, when the latest import was blocked for review, or when
records were set aside, and red when the latest import failed or none has
happened. It uses the same freshness rules as the API.

## Same-name flag

Students who share a first and last name in the same term (ignoring case and
extra spaces) are marked in the list and can be filtered. This is only a
flag: same-name students are different people, and identity is decided by the
student ID, never by name.

## Status override

Select students, choose **Change status (a reason is required)**, pick a
status, and give a reason of at least 10 characters. Each change is written to
the audit log with the admin's username, the old and new status, and the
reason.

The source remains the authority, so a later import can reverse an override:

- An active student missing from the file is deactivated again.
- An inactive student present in the file is reactivated.
- A student held for review stays held until an administrator changes them.

Both the override and the later change appear in the audit log.

## Safeguards

- Existing students are read-only in the admin form, so status changes go
  through the override action and everything else comes from imports.
- Students cannot be deleted in the admin.
- Students entered by hand are audited and get a warning that the next import
  will deactivate them unless the source lists them.
- The audit log is read-only.