"""Replay a change to the fictional schedule in a disposable packet."""

from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

from audit_packet import audit_packet


EXAMPLE = Path(__file__).resolve().parent / "examples" / "fictional-quarter"


def show_results(stage, report):
    print(stage)
    for item in report["evidence"]:
        detail = item.get("detail") or f"captured {item['captured_at']}"
        print(f"  {item['id']}: {item['result']} ({detail})")


def run_demo():
    with TemporaryDirectory(prefix="heltemes-cutoff-") as temporary:
        case = Path(temporary) / "fictional-quarter"
        shutil.copytree(EXAMPLE, case, symlinks=True)
        manifest = case / "packet.json"
        baseline = audit_packet(manifest)
        print(f"Decision cutoff: {baseline['cutoff']}")
        show_results("Original packet", baseline)
        outcomes = {item["id"]: item["result"] for item in baseline["evidence"]}
        if outcomes != {
            "pre-release-note": "admitted",
            "quarterly-statement": "late",
            "call-transcript": "unavailable",
        }:
            raise ValueError("The starting packet differs from the published exercise.")

        schedule = case / "evidence" / "pre-release-note.txt"
        if schedule.is_symlink() or schedule.parent.is_symlink():
            raise ValueError("The schedule must be a regular file inside the disposable packet.")
        original = schedule.read_bytes()
        schedule.write_bytes(original + b"Revised schedule: results are delayed.\n")
        changed = audit_packet(manifest)
        show_results("After editing the schedule", changed)
        items = {item["id"]: item for item in changed["evidence"]}
        if (changed["integrity_ok"] or items["pre-release-note"]["result"] != "integrity_error"
                or items["pre-release-note"].get("detail") != "SHA-256 mismatch."):
            raise ValueError("Expected a fingerprint mismatch for the changed schedule.")

        schedule.write_bytes(original)
        restored = audit_packet(manifest)
        if restored != baseline:
            raise ValueError("Restoring the original bytes did not reproduce the baseline audit.")
        print("Restored original bytes: the full audit matches the baseline.")


if __name__ == "__main__":
    try:
        run_demo()
    except (OSError, ValueError) as error:
        sys.exit(f"Demo stopped: {error}")
