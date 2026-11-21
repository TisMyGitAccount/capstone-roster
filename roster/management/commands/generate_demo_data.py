import json
import random
import re
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand
from faker import Faker

OUT_DIR = Path(__file__).resolve().parents[2] / "demo_data"
TERM = "FA26"
FAKE_ID_BASE = 9000000  # 7-digit, digits-only fake IDs


def clean(text):
    """Lowercase letters only, so emails stay valid (e.g. O'Connor -> oconnor)."""
    return re.sub(r"[^a-z]", "", text.lower())


def build(n, first, last):
    return {
        "panthersoft_id": str(FAKE_ID_BASE + n),
        "first_name": first,
        "last_name": last,
        "email": f"{clean(first)}.{clean(last)}.{n}@example.edu",
        "term": TERM,
    }


def save(name, students):
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / name
    path.write_text(json.dumps(students, indent=2), encoding="utf-8")
    return path


class Command(BaseCommand):
    help = "Generate fake Panthersoft roster snapshots (fixed seed, reproducible)."

    def handle(self, *args, **options):
        rng = random.Random(42)
        Faker.seed(42)
        fake = Faker()

        # Snapshot 1: 294 unique students plus 6 same-name duplicates = 300
        snap1 = [build(n, fake.first_name(), fake.last_name()) for n in range(1, 295)]
        n = 295
        for original in rng.sample(snap1, 6):
            snap1.append(build(n, original["first_name"], original["last_name"]))
            n += 1
        rng.shuffle(snap1)

        # Snapshot 2: drops, new enrollments, and changes
        snap2 = [dict(s) for s in snap1]
        dropped = {s["panthersoft_id"] for s in rng.sample(snap2, 8)}
        snap2 = [s for s in snap2 if s["panthersoft_id"] not in dropped]

        changed = rng.sample(snap2, 7)
        for s in changed[:5]:  # email changes
            s["email"] = (
                f"{clean(s['first_name'])}.{clean(s['last_name'])}"
                f".{s['panthersoft_id'][-6:]}.new@example.edu"
            )
        for s in changed[5:]:  # last-name changes
            s["last_name"] = fake.last_name()

        n = 301
        for _ in range(12):  # new enrollments
            snap2.append(build(n, fake.first_name(), fake.last_name()))
            n += 1
        twin = rng.choice(snap2[:-12])  # one new student shares an existing name
        snap2.append(build(n, twin["first_name"], twin["last_name"]))
        rng.shuffle(snap2)

        # Snapshot 3: a bad export missing roughly 45% of students
        snap3 = rng.sample(snap2, int(len(snap2) * 0.55))

        # Dirty snapshot: snapshot 2 plus messy records (no randomness used)
        latest = {s["panthersoft_id"]: s for s in snap1}
        latest.update({s["panthersoft_id"]: s for s in snap2})
        names = Counter((s["first_name"], s["last_name"]) for s in latest.values())
        unique_name = next(k for k, c in names.items() if c == 1)
        shared_name = next(k for k, c in names.items() if c > 1)

        dirty = [dict(s) for s in snap2]
        for s in dirty[:3]:  # padded IDs: should still match their students
            s["panthersoft_id"] = f"  {s['panthersoft_id']}  "
        dirty.extend([
            # letters in an ID -> invalid_id
            {**build(400, "Letter", "Id"), "panthersoft_id": "S9000400"},
            # partial ID -> invalid_id
            {**build(401, "Partial", "Id"), "panthersoft_id": "90004"},
            # blank ID, one student has that name -> missing_id
            {**build(402, *unique_name), "panthersoft_id": ""},
            # blank ID, several students have that name -> ambiguous
            {**build(403, *shared_name), "panthersoft_id": ""},
            # same ID appears twice -> duplicate (both copies)
            {**snap2[20], "email": "copy.of.record@example.edu"},
            # email already used by another student -> conflict (both records)
            {**build(404, "Email", "Clash"), "email": snap2[30]["email"]},
        ])

        for name, data in [
            ("snapshot_1.json", snap1),
            ("snapshot_2.json", snap2),
            ("snapshot_3_mass_drop.json", snap3),
            ("snapshot_dirty.json", dirty),
        ]:
            save(name, data)
            self.stdout.write(f"{name}: {len(data)} records")

        self.stdout.write(self.style.SUCCESS(f"Written to {OUT_DIR}"))