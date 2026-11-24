"""Recalculate the outage case study's aggregate metrics from the public CSVs."""

import csv
from decimal import Decimal
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
SAMPLE_COLUMNS = ("elapsed_seconds", "source", "pending", "deferred", "accepted", "attempts", "transport_errors")
EVENTS = ("started", "receiver_stopped", "receiver_restarted", "sender_killed",
          "sender_restarted", "final_steady_started", "finished")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rows(path, columns):
    with path.open(encoding="utf-8", newline="") as handle:
        data = csv.DictReader(handle)
        require(tuple(data.fieldnames or ()) == columns, f"Unexpected columns in {path.name}.")
        result = list(data)
        require(all(None not in row and None not in row.values() for row in result),
                f"Unexpected number of fields in {path.name}.")
        return result


def measure(directory, record):
    events = rows(directory / "events.csv", ("elapsed_seconds", "event"))
    require(tuple(row["event"] for row in events) == EVENTS, "Unexpected event sequence.")
    clock = {row["event"]: Decimal(row["elapsed_seconds"]) for row in events}
    times = list(clock.values())
    require(times[0] >= 0 and all(a < b for a, b in zip(times, times[1:])), "Events out of order.")
    samples = rows(directory / "samples.csv", SAMPLE_COLUMNS)
    require(samples, "No samples available.")
    for sample in samples:
        sample["elapsed_seconds"] = Decimal(sample["elapsed_seconds"])
        for key in SAMPLE_COLUMNS[1:]:
            sample[key] = int(sample[key])
            require(sample[key] >= 0, "Negative sample count.")
        require(0 <= sample["elapsed_seconds"] <= clock["finished"]
                and sample["accepted"] <= sample["source"] <= record["expected_alerts"]
                and sample["pending"] <= record["queue_limit"]
                and sample["pending"] + sample["deferred"] <= sample["source"]
                and sample["transport_errors"] <= sample["attempts"], "Sample outside its bounds.")
    for previous, current in zip(samples, samples[1:]):
        require(all(previous[key] <= current[key] for key in
                    ("elapsed_seconds", "source", "accepted", "attempts", "transport_errors")),
                "An elapsed time or cumulative count went backwards.")
    final = samples[-1]
    require(final["source"] == final["accepted"] == record["expected_alerts"]
            and final["pending"] == final["deferred"] == 0, "Final counts disagree.")
    stopped, restart = clock["receiver_stopped"], clock["receiver_restarted"]
    outage = [s for s in samples if stopped <= s["elapsed_seconds"] < restart]
    require(outage and all(s["accepted"] == outage[0]["accepted"] for s in outage),
            "Expected a receiver outage with a stable accepted count.")
    target = outage[-1]["source"]
    require(target > outage[-1]["accepted"], "No backlog was observed during the outage.")
    drain = next((s["elapsed_seconds"] for s in samples if s["elapsed_seconds"] >= restart
                  and s["accepted"] == s["source"] == target and s["pending"] == s["deferred"] == 0), None)
    require(drain is not None, "No sample shows that the outage backlog drained.")
    return {
        "samples": len(samples), "peak_pending": max(s["pending"] for s in samples),
        "peak_deferred": max(s["deferred"] for s in samples), "outage_source": target,
        "outage_accepted": outage[-1]["accepted"], "final_source": final["source"],
        "final_accepted": final["accepted"], "final_pending": final["pending"],
        "final_deferred": final["deferred"], "attempts": final["attempts"],
        "transport_errors": final["transport_errors"],
        "first_drained_sample_seconds": str(drain), "sampled_drain_after_restart_seconds": str(drain - restart),
        "receiver_outage_seconds": str(restart - stopped),
    }


if __name__ == "__main__":
    try:
        record = json.loads((HERE / "summary.json").read_text(encoding="utf-8"))
        metrics = measure(HERE, record)
        require(metrics == record["metrics"], "Published metrics disagree with the CSVs.")
        print(json.dumps(metrics, indent=2))
    except (ArithmeticError, OSError, KeyError, TypeError, ValueError) as error:
        sys.exit(f"Public check failed: {error}")
