# Verification record — version 2.0.0

## Scope

The release is verified on Windows x64 with Python 3.12. Automated tests use temporary SQLite databases and fake YouTube responses. They do not authorize a Google account or moderate real comments.

## Automated checks

Tests cover Unicode matching, regex limits, author allowlists, pagination and resume, replies, cancellation, 50-ID batches, ownership, uncertain-write recovery, scheduler failures, local API authorization, import/export, Google endpoint validation, REST retries, and Windows DPAPI round trips.

Release checks exercise demo and disconnected normal startup from the bundled EXE, with Python and developer tools removed from the child process PATH. This verifies bundling on the build host; it is not a clean-machine or every-Windows-version certification.

Validation performed on October 28, 2026:

| Check | Result |
|---|---|
| `python -m pytest -q` | 51 passed; one upstream Starlette TestClient deprecation warning |
| `python -m compileall -q cleaner` | Passed |
| `node --check cleaner/static/app.js` | Passed |
| PyInstaller Windows x64 single-file build | Passed |
| Bundled EXE: offline demo | Passed: 48 comments/replies, 3 simulated holds, bounded rescan, CSV, clean shutdown |
| Bundled EXE: normal mode | Passed: fresh disconnected startup, local rules, CSV, clean shutdown |
| Windows instance locking | Regression test covers second launch and reopening after release of the lock |
| Final EXE: second launch | Passed in both normal and demo modes; original service remains running |
| Final EXE: credential storage | Passed: synthetic Desktop-client JSON encrypted with DPAPI; no Google login or token created |
| Browser UI against the bundled EXE | Passed: navigation, search, bulk selection, confirmation, three handled records, action journal, rule add/remove, schedule enable/pause, disabled demo Google controls |
| Browser console during those checks | No warnings or errors recorded |

The browser screenshot in `docs/demo-overview.png` shows the resulting offline workspace. No live comments were modified.

The second-launch test exposed a Windows locked-byte read error during development. The launcher now checks the file length without reading the locked byte; the regression test and final executable checks cover this path.

## Live-account limitation

No Google OAuth Desktop client or live YouTube channel was supplied for this rewrite. Google consent, refresh-token issuance, channel/Brand Account selection, real comment visibility, production quota behavior, and real moderation effects remain unverified. Validate these on a user-owned test channel before enabling production automatic cleaning.

The adapter is tested against documented REST contracts. Offline demo moderation is explicitly simulated and does not establish live API success.

## Distribution

The Windows executable is unsigned. Release ZIP and executable checksums are supplied. Dependency notices are included. The release contains no Google credentials, tokens, account data, or local build environment.
