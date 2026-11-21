import json
import random
import re
from pathlib import Path

from django.core.management.base import BaseCommand
from faker import Faker

OUT_DIR = Path(__file__).resolve().parents[2] / "demo_data"
TERM = "FA26"


def clean(text):
    """Lowercase letters only, so emails stay valid (e.g. O'Connor -> oconnor)."""
    return re.sub(r"[^a-z]", "", text.lower())


def build(n, first, last):
    return {
        "panthersoft_id": f"DEMO{n:06d}",
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

        for name, data in [
            ("snapshot_1.json", snap1),
            ("snapshot_2.json", snap2),
            ("snapshot_3_mass_drop.json", snap3),
        ]:
            save(name, data)
            self.stdout.write(f"{name}: {len(data)} students")

        self.stdout.write(self.style.SUCCESS(f"Written to {OUT_DIR}"))