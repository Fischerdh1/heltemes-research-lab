"""Audit the integrity and research cutoff of a synthetic evidence packet."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys


class PacketError(ValueError):
    """The packet does not follow the demo format."""


def require(condition, message):
    if not condition:
        raise PacketError(message)


def timestamp(value, field):
    require(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value),
            f"{field} must be a UTC timestamp ending in Z.")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise PacketError(f"{field} is not a valid date and time.") from error


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def check_entry(entry, directory, cutoff):
    identity = entry["id"]
    if entry.get("status") == "unavailable":
        require(set(entry) == {"id", "status", "reason"} and isinstance(entry["reason"], str)
                and entry["reason"].strip(), f"{identity} needs a reason for its unavailable status.")
        return {"id": identity, "result": "unavailable", "detail": entry["reason"]}

    require(set(entry) == {"id", "status", "path", "published_at", "captured_at", "sha256"}
            and entry["status"] == "captured", f"{identity} has invalid captured evidence fields.")
    published = timestamp(entry["published_at"], f"{identity} published_at")
    captured = timestamp(entry["captured_at"], f"{identity} captured_at")
    require(published <= captured, f"{identity} was captured before the declared publication time.")
    name, expected = entry["path"], entry["sha256"]
    require(isinstance(name, str) and re.fullmatch(r"evidence/[a-z0-9][a-z0-9_.-]*", name),
            f"{identity} must reference a single file in evidence/.")
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected),
            f"{identity} must declare a lowercase SHA-256 digest.")

    file = directory / name
    if file.parent.is_symlink() or file.is_symlink() or not file.is_file():
        return {"id": identity, "result": "integrity_error", "detail": "Evidence file missing or unsafe."}
    with file.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != expected:
        return {"id": identity, "result": "integrity_error", "detail": "SHA-256 mismatch."}

    result = "admitted" if captured <= cutoff else "late"
    return {"id": identity, "result": result, "published_at": entry["published_at"],
            "captured_at": entry["captured_at"], "sha256": actual}


def audit_packet(manifest):
    with manifest.open(encoding="utf-8") as handle:
        packet = json.load(handle, object_pairs_hook=unique_object)
    require(isinstance(packet, dict)
            and set(packet) == {"version", "synthetic", "case", "cutoff", "entries"},
            "Unexpected packet fields.")
    require(type(packet["version"]) is int and packet["version"] == 1 and packet["synthetic"] is True,
            "Expected a version 1 synthetic packet.")
    require(isinstance(packet["case"], str) and packet["case"].strip(), "Packet needs a case name.")
    cutoff = timestamp(packet["cutoff"], "cutoff")
    require(isinstance(packet["entries"], list) and packet["entries"], "Packet needs evidence entries.")

    seen = set()
    evidence = []
    for entry in packet["entries"]:
        require(isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"].strip(),
                "Each entry needs an ID.")
        require(entry["id"] not in seen, f"Duplicate evidence ID: {entry['id']}")
        seen.add(entry["id"])
        evidence.append(check_entry(entry, manifest.parent, cutoff))

    counts = Counter(item["result"] for item in evidence)
    return {"case": packet["case"], "cutoff": packet["cutoff"], "integrity_ok": counts["integrity_error"] == 0,
            "counts": {key: counts[key] for key in ("admitted", "late", "unavailable", "integrity_error")},
            "evidence": evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to a synthetic packet manifest.")
    args = parser.parse_args()
    try:
        report = audit_packet(args.manifest)
    except (OSError, ValueError) as error:
        print(f"Packet audit stopped: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["integrity_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
