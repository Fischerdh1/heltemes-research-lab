# HELTEMES Research Lab

A public companion to HELTEMES Evidence for reproducible earnings research. The lab demonstrates how to check which source files were available at a declared decision time and whether their bytes still match the saved record. It uses a fictional company and runs offline with Python's standard library.

## Run the audit

Use Python 3.11 or newer from the repository root.

```sh
python3 audit_packet.py examples/fictional-quarter/packet.json
python3 -B -m unittest discover -s tests -v
```

The fictional decision cutoff is **14:25 UTC**. The audit reports one admission, one late item, and one unavailable item.

| Evidence | Timeline | Audit result |
| --- | --- | --- |
| Pre-release schedule | Published at 14:15, captured at 14:18 | Admitted |
| Quarterly statement | Published at 14:30, captured at 14:32 | Late |
| Call transcript | No capture | Unavailable |

## How it works

The [sample manifest](examples/fictional-quarter/packet.json) records each capture's publication time, capture time, and SHA-256 digest. The audit checks the file's current digest first. It admits a matching file when its capture time is at or before the cutoff. A file published early can still be late if it was captured after the cutoff. Missing evidence stays explicit.

The command prints JSON for inspection or reuse. Exit code `0` means that the manifest was valid and all declared captures matched their digests. Exit code `1` flags a missing or altered capture. Exit code `2` flags an invalid or unreadable packet.

The tamper test edits a temporary copy and verifies that the CLI reports an integrity error. A digest check relies on a reference manifest obtained from a trusted source. The example also takes the date fields in that manifest as declared timestamps. Establishing source authenticity, independent timestamps, or trust in the manifest requires separate controls.

The examples and dates are fictional. The lab covers evidence timing and integrity checks for research records.
