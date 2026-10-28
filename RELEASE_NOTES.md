# Version 2.0.0

YouTube Spam Cleaner now runs as a local browser application with a bundled Windows x64 executable. Download the Windows ZIP from Releases, extract it, and open `YouTubeSpamCleaner.exe`. No Python installation or compilation is required. `Demo.cmd` opens an isolated offline sample channel.

- Replaces the PyQt interface with an English browser workspace for review, rules, scheduling, connection, and history.
- Adds paginated thread/reply scanning, saved resume cursors, bounded jobs, and cancellation.
- Adds Unicode-aware matching, phrases, bounded regex rules, author allowlists, and legacy keyword import.
- Uses channel-owner moderation actions: hold, reject, reject with author ban, and publish held comments.
- Persists rules, results, schedules, jobs, and an action journal in SQLite. Unknown write outcomes require manual reconciliation before retry.
- Protects Windows OAuth credentials with DPAPI and keeps the server on loopback with a per-launch session capability.

Existing keyword files can be imported. Old GUI settings and login sessions are not automatically migrated. The previous source remains in Git history.

Validation: 51 automated tests, packaged normal/demo checks, and browser interaction checks. See `VERIFICATION.md` for exact coverage and limitations. Actual Google consent and real YouTube moderation were not tested; real use requires your own Google OAuth Desktop client and connected channel. The executable is unsigned.
