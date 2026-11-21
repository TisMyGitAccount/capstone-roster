# Identity Rules

These rules define how the roster decides whether two records are the same
student. They are enforced in code and each one is covered by a named test.

## Assumptions

- **The source (Panthersoft) is the authority.** The roster is a verifiable
  copy of it, never the other way around.
- **Student IDs are digits only** (0-9) and exactly 7 digits long by default
  (`ROSTER_ID_LENGTH` in settings). Digits have no case.
- **Names are display-only.** They never decide identity.
- **The demo runs on simulated data.** A real source adapter only needs to
  provide `fetch_enrolled(term)`; the rules below apply unchanged.

## Rules, as implemented

| Rule | Statement | Enforced in | Test |
|---|---|---|---|
| ID-01 | A record must carry one stable identifier. A record with a blank ID is set aside as an issue; the rest of the sync continues. | `sync._classify` | `test_ID_01_blank_id_is_quarantined_not_created` |
| ID-02 | Each identifier is unique. The database refuses a second student with the same ID. | `Student.panthersoft_id` (`unique=True`) | `test_ID_02_database_rejects_duplicate_ids` |
| ID-03 | Identifiers are compared only after normalization. | `identity.normalize_id`, called in `sync._classify` | `test_ID_03_04_whitespace_does_not_change_identity` |
| ID-04 | Leading and trailing whitespace never changes identity. | `identity.normalize_id` | `test_ID_03_04_whitespace_does_not_change_identity` |
| ID-05 | Any character other than the digits 0-9 makes an ID invalid, in any case and including non-ASCII digits. | `identity.id_problem` | `test_ID_05_letters_make_an_id_invalid_in_any_case`, `test_ID_05_non_ascii_digits_are_invalid` |
| ID-06 | A partial identifier never matches. IDs must be exactly the expected length. | `identity.id_problem` | `test_ID_06_partial_id_never_matches` |
| ID-07 | With no ID, the fallback fields (first and last name) are used together, as suggestions only. | `identity.fallback_candidates` | `test_ID_07_08_09_fallback_suggests_but_never_merges` |
| ID-08 | A fallback candidate requires every fallback component to match after normalization. | `identity.fallback_candidates` | `test_ID_07_08_09_fallback_suggests_but_never_merges` |
| ID-09 | A missing component never matches anything. | `identity.fallback_candidates` | `test_ID_07_08_09_fallback_suggests_but_never_merges` |
| ID-10 | A record resolves to at most one identity. ID matching uses one key; fallback never selects a match. | `sync._classify`, `sync._plan` | `test_ID_10_15_ambiguous_matches_select_nothing` |
| ID-11 | Two source records with the same normalized ID are classified as duplicates. Neither is applied. | `sync._classify` | `test_ID_11_same_id_twice_is_classified_as_duplicate` |
| ID-12 | A source record with no roster match is classified as new and added, because the source is the authority. | `sync._plan`, `sync._apply` | `test_ID_12_new_source_record_is_added` |
| ID-13 | A roster student absent from the source is classified as missing and deactivated, with an audit entry. | `sync._plan`, `sync._apply` | `test_ID_13_roster_student_missing_from_source_is_deactivated` |
| ID-14 | Identity data that points to different people is a conflict and is never merged. | `sync._classify` | `test_ID_14_email_owned_by_a_different_student_is_a_conflict`, `test_ID_14_two_source_records_sharing_an_email_both_conflict` |
| ID-15 | Multiple plausible matches are ambiguous. No candidate is selected or prioritized. | `sync._classify` | `test_ID_10_15_ambiguous_matches_select_nothing` |
| ID-16 | Normalization removes only whitespace. Hyphens, leading zeros, and other characters stay significant. | `identity.normalize_id` | `test_ID_16_significant_characters_are_never_stripped` |

## Wording changes from the original rule set

- **ID-05** originally read "Case differences do not change the identity if
  identifier convention is case-sensitive", which reads backwards. IDs are
  digits only, so the rule became: any non-digit makes the ID invalid.
- **ID-12** originally classified a source record with no roster match as
  "unexpected". Because the source is the authority, it is now classified as
  new and added.
- **ID-11** originally used `S123` and `s123` as its example. With digit-only
  IDs the equivalent is `9000001` and `"  9000001  "`, which normalize to the
  same ID.

## What happens to a record that fails a rule

A record that breaks a rule is set aside as a **sync issue** (visible in the
admin under *Sync issues*) instead of failing the whole sync.

| Issue kind | Cause |
|---|---|
| `invalid_id` | Letters, symbols, or the wrong length (ID-05, ID-06, ID-16) |
| `missing_id` | Blank ID (ID-01), with zero or one suggested match (ID-07 to ID-09) |
| `ambiguous` | Blank ID with several suggested matches (ID-15) |
| `duplicate` | The same normalized ID appears more than once (ID-11) |
| `conflict` | An email is claimed by a different student (ID-14) |
| `invalid_record` | A required field is empty |

Students whose ID appears in a set-aside record are **not** deactivated as
missing, since the source did mention them.

## Safeguards around the rules

- A source that returns no students leaves the roster untouched.
- If more than 10% of source records are unusable, the whole sync is refused,
  on the assumption that the source format has changed
  (`ROSTER_SYNC_REJECT_THRESHOLD`).
- If a sync would deactivate more than 10% of active students, it is blocked
  for admin review (`ROSTER_SYNC_DEACTIVATION_THRESHOLD`).
- Any error rolls the sync back, so the previous roster stays intact.
- Every add, update, and deactivation is recorded in the audit log.

## Known limitations

- **ID-14 only checks email.** It is the only secondary identity field the
  roster stores, so conflicts on other fields are not detected.
- **Fallback matching uses names only.** No date of birth is stored, by design.
  Name matching is why fallback results are suggestions and never merges.
- **Hand-entered students in the admin** are checked for digits only. Length
  and whitespace rules are applied during sync, not on manual entry.
- **ID-11 is tested with an exact duplicate.** A padded duplicate
  (`"  9000001  "` alongside `9000001`) is handled by the same code path
  because normalization runs first, but has no dedicated test yet.

## Verifying

Run every test:

    python manage.py test

Run only the identity rule tests:

    python manage.py test roster.tests.IdentityRuleTests

To see the rules act on messy data, sync `snapshot_dirty.json` and open
*Sync issues* in the admin.