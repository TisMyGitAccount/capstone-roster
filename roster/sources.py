import csv
import io
import json
import re
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent / "demo_data"
MAX_CSV_ROWS = 20000


class SourceError(Exception):
    """Raised when the source can't be reached or returns unusable data."""


class MockPanthersoftSource:
    """Stands in for Panthersoft by reading a demo snapshot file.

    A real adapter would expose the same method:
        fetch_enrolled(term) -> list of dicts with the keys
        panthersoft_id, first_name, last_name, email, term
    """

    def __init__(self, snapshot):
        self.snapshot = snapshot

    def fetch_enrolled(self, term):
        if self.snapshot == "fail":
            raise SourceError("Simulated Panthersoft outage")
        path = DEMO_DIR / self.snapshot
        if not path.exists():
            raise SourceError(f"Snapshot not found: {self.snapshot}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return [record for record in data if record.get("term") == term]


# Column names a file may use, after lowercasing and turning spaces and
# punctuation into "_". Anything else is an extra column and is ignored.
HEADER_ALIASES = {
    "panthersoft_id": {"panthersoft_id", "student_id", "id", "emplid"},
    "first_name": {"first_name", "first", "firstname", "given_name"},
    "last_name": {"last_name", "last", "lastname", "surname", "family_name"},
    "email": {"email", "email_address", "e_mail"},
    "term": {"term", "semester"},
}
REQUIRED_COLUMNS = ("panthersoft_id", "first_name", "last_name", "email")
_FIELD_FOR_HEADER = {
    alias: field for field, aliases in HEADER_ALIASES.items() for alias in aliases
}


def _canonical(header):
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


class CsvSource:
    """Reads an exported roster file. Same contract as the mock source."""

    def __init__(self, content):
        self.content = content  # the file's bytes

    def fetch_enrolled(self, term):
        wanted = term.strip().upper()
        try:
            text = self.content.decode("utf-8-sig").strip()  # also drops Excel's BOM
        except UnicodeDecodeError:
            raise SourceError(
                "The file is not UTF-8 text. In Excel, choose "
                "'Save As > CSV UTF-8 (Comma delimited)'."
            )
        if not text:
            raise SourceError("The file is empty.")

        delimiter = max(",;\t", key=text.splitlines()[0].count)
        try:
            return self._read(csv.reader(io.StringIO(text), delimiter=delimiter), wanted)
        except csv.Error as exc:
            raise SourceError(f"The file could not be read as CSV: {exc}")

    @staticmethod
    def _read(rows, wanted):
        header = next(rows)
        columns = {}
        for position, name in enumerate(header):
            field = _FIELD_FOR_HEADER.get(_canonical(name))
            if field is None:
                continue
            if field in columns:
                raise SourceError(f"The file has more than one '{field}' column.")
            columns[field] = position

        missing = [c for c in REQUIRED_COLUMNS if c not in columns]
        if missing:
            found = ", ".join(h.strip() for h in header if h.strip()) or "none"
            raise SourceError(
                f"The file is missing required columns: {', '.join(missing)}. "
                f"Columns found: {found}."
            )

        records, terms_seen, count = [], set(), 0
        for row in rows:
            if not any(cell.strip() for cell in row):
                continue  # blank line
            count += 1
            if count > MAX_CSV_ROWS:
                raise SourceError(f"The file has more than {MAX_CSV_ROWS} rows.")
            record = {
                field: (row[pos].strip() if pos < len(row) else "")
                for field, pos in columns.items()
            }
            row_term = record.get("term", "").upper() or wanted
            terms_seen.add(row_term)
            if row_term != wanted:
                continue
            record["term"] = row_term
            records.append(record)

        if count == 0:
            raise SourceError("The file has a header but no student rows.")
        if not records:
            raise SourceError(
                f"No rows for term {wanted} (terms in the file: "
                f"{', '.join(sorted(terms_seen))})."
            )
        return records