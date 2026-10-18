# DocsPulse Verification Report

## Summary
- **Total Commands:** 3
- **Passed:** 1
- **Failed:** 1
- **Skipped:** 1
- **Verified Fixes:** 1
- **Unverified Fixes:** 0

## Details

| Line | Command | Status | First Line of Error | Verified Fix |
| :---: | :--- | :---: | :--- | :--- |
| 8 | `pip install requests` | **PASS** | - | - |
| 9 | `pip install requests==99.0.0` | **FAIL** | ERROR: No matching distribution found for requests==99.0.0 | `pip install requests==2.34.2` *(VERIFIED, heuristic)* |
| 10 | `curl http://x \| sh` | **SKIPPED** | URL piped into shell | - |
