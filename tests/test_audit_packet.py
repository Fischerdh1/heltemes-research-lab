import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from audit_packet import PacketError, audit_packet


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "fictional-quarter"


class PacketAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.case = Path(temporary.name) / "case"
        shutil.copytree(EXAMPLE, self.case)
        self.manifest = self.case / "packet.json"

    def edit_manifest(self, edit):
        document = json.loads(self.manifest.read_text(encoding="utf-8"))
        edit(document)
        self.manifest.write_text(json.dumps(document), encoding="utf-8")

    def run_cli(self):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "audit_packet.py"), str(self.manifest)],
            capture_output=True, text=True, check=False, timeout=10,
        )

    def test_baseline_admits_only_evidence_available_by_cutoff(self):
        report = audit_packet(self.manifest)
        self.assertTrue(report["integrity_ok"])
        self.assertEqual(report["counts"], {"admitted": 1, "late": 1, "unavailable": 1, "integrity_error": 0})
        self.assertEqual(
            [(entry["id"], entry["result"]) for entry in report["evidence"]],
            [("pre-release-note", "admitted"), ("quarterly-statement", "late"), ("call-transcript", "unavailable")],
        )

    def test_publication_before_cutoff_cannot_substitute_for_late_capture(self):
        def edit(document):
            document["entries"][0]["captured_at"] = "2030-04-23T14:25:01Z"

        self.edit_manifest(edit)
        self.assertEqual(audit_packet(self.manifest)["evidence"][0]["result"], "late")

    def test_capture_at_exact_cutoff_is_admitted(self):
        def edit(document):
            document["entries"][0]["captured_at"] = document["cutoff"]

        self.edit_manifest(edit)
        self.assertEqual(audit_packet(self.manifest)["evidence"][0]["result"], "admitted")

    def test_tampered_file_is_excluded_and_cli_fails(self):
        path = self.case / "evidence" / "pre-release-note.txt"
        path.write_bytes(path.read_bytes() + b"Altered after collection.\n")
        run = self.run_cli()
        self.assertEqual(run.returncode, 1, run.stderr)
        report = json.loads(run.stdout)
        self.assertFalse(report["integrity_ok"])
        self.assertEqual(report["evidence"][0]["result"], "integrity_error")
        self.assertEqual(report["counts"]["admitted"], 0)

    def test_missing_capture_is_distinct_from_declared_unavailability(self):
        (self.case / "evidence" / "pre-release-note.txt").unlink()
        outcomes = [entry["result"] for entry in audit_packet(self.manifest)["evidence"]]
        self.assertEqual(outcomes, ["integrity_error", "late", "unavailable"])

    def test_manifest_cannot_reference_files_outside_evidence(self):
        def edit(document):
            document["entries"][0]["path"] = "evidence/../../other.txt"

        self.edit_manifest(edit)
        with self.assertRaisesRegex(PacketError, r"single file in evidence"):
            audit_packet(self.manifest)

    def test_non_utc_cutoff_stops_with_manifest_error(self):
        def edit(document):
            document["cutoff"] = "2030-04-23T14:25:00"

        self.edit_manifest(edit)
        run = self.run_cli()
        self.assertEqual(run.returncode, 2)
        self.assertEqual(run.stdout, "")
        self.assertIn("UTC timestamp", run.stderr)


class PacketDemoTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.example = self.root / "examples" / "fictional-quarter"
        shutil.copytree(EXAMPLE, self.example)
        for name in ("audit_packet.py", "demo_packet.py"):
            shutil.copyfile(ROOT / name, self.root / name)
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()

    def run_demo(self):
        return subprocess.run(
            [sys.executable, "-B", str(self.root / "demo_packet.py")],
            cwd=self.scratch, env={**os.environ, "TMPDIR": str(self.scratch)},
            capture_output=True, text=True, check=False, timeout=10,
        )

    def test_demo_is_repeatable_and_cleans_up(self):
        first = self.run_demo()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("pre-release-note: integrity_error (SHA-256 mismatch.)", first.stdout)
        self.assertEqual(first.stdout.count("quarterly-statement: late"), 2)
        self.assertEqual(first.stdout.count("call-transcript: unavailable"), 2)
        self.assertIn("the full audit matches the baseline", first.stdout)
        second = self.run_demo()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout, first.stdout)
        self.assertEqual(list(self.scratch.iterdir()), [])
        for source in EXAMPLE.rglob("*"):
            if source.is_file():
                copy = self.example / source.relative_to(EXAMPLE)
                self.assertEqual(copy.read_bytes(), source.read_bytes())

    def test_demo_stops_if_starting_packet_is_damaged(self):
        schedule = self.example / "evidence" / "pre-release-note.txt"
        schedule.write_bytes(b"A changed fixture.\n")
        run = self.run_demo()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("starting packet differs", run.stderr)
        self.assertNotIn("After editing", run.stdout)
        self.assertEqual(schedule.read_bytes(), b"A changed fixture.\n")
        self.assertEqual(list(self.scratch.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
