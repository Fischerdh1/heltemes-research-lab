"""Verify the public outage study using only the files published with it."""
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CASE = Path(__file__).resolve().parents[1] / "case-studies" / "alert-outage"


class OutageCaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.case = Path(temp.name)
        for name in ("check.py", "samples.csv", "events.csv", "summary.json"):
            shutil.copyfile(CASE / name, self.case / name)
        self.summary = self.case / "summary.json"

    def check(self):
        return subprocess.run(
            [sys.executable, "-I", "-S", "-B", str(self.case / "check.py")],
            capture_output=True, text=True, timeout=10,
        )

    def test_published_timeline_reproduces_summary(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        metrics = json.loads(result.stdout)
        self.assertEqual(metrics, json.loads(self.summary.read_text())["metrics"])
        self.assertEqual((metrics["final_source"], metrics["final_accepted"]), (702, 702))
        self.assertEqual((metrics["final_pending"], metrics["final_deferred"]), (0, 0))

    def test_reports_a_missing_final_acceptance(self):
        samples = self.case / "samples.csv"
        with samples.open(newline="") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames
            rows = list(reader)
        rows[-1]["accepted"] = str(int(rows[-1]["accepted"]) - 1)
        with samples.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Public check failed", result.stderr)

    def test_reports_a_misstated_recovery_time(self):
        record = json.loads(self.summary.read_text())
        record["metrics"]["sampled_drain_after_restart_seconds"] = "0"
        self.summary.write_text(json.dumps(record))
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Published metrics disagree", result.stderr)
