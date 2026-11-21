import json
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent / "demo_data"


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