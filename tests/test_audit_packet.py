import json
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


if __name__ == "__main__":
    unittest.main()
