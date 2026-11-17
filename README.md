# HELTEMES Research Lab

[![Verify research examples](https://github.com/Fischerdh1/heltemes-research-lab/actions/workflows/verify.yml/badge.svg?branch=main)](https://github.com/Fischerdh1/heltemes-research-lab/actions/workflows/verify.yml)

Which files were available at a research cutoff, and do their contents still match the saved record? This Python command-line tool answers both questions for a fictional earnings packet. It runs offline with the Python standard library.

## Quick start

Use Python 3.11 or newer.

```sh
git clone https://github.com/Fischerdh1/heltemes-research-lab.git
cd heltemes-research-lab
python3 audit_packet.py examples/fictional-quarter/packet.json
```

The example records a decision cutoff of **14:25 UTC**.

| Evidence | Timeline (UTC) | Result |
| --- | --- | --- |
| Pre-release schedule | Published 14:15, captured 14:18 | Admitted |
| Quarterly statement | Published 14:30, captured 14:32 | Late |
| Call transcript | No capture | Unavailable |

## Verification rules

The [packet manifest](examples/fictional-quarter/packet.json) records each file's publication time, capture time, and SHA-256 digest. The audit checks the bytes against the digest and uses the **capture time** to determine whether the file was available by the cutoff. A document can be published before the cutoff and still be captured too late.

The digest check assumes a trusted reference manifest. The audit uses the timestamps declared there. Source authenticity, independent timestamping, and manifest custody require separate controls.

| Exit code | Meaning |
| --- | --- |
| `0` | The manifest is valid and all declared captures match. See the JSON for late and unavailable items. |
| `1` | A declared capture is missing or differs from its saved digest. |
| `2` | The packet is invalid or unreadable. |

## Tests

```sh
python3 -B -m unittest discover -s tests -v
```

The tests cover altered and missing files, captures at and just after the cutoff, invalid timestamps, and paths outside the evidence directory.
