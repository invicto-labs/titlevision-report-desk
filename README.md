# TitleVision Report Desk

Windows application for collecting and validating TitleVision's latest completed workdays'
error report. It includes contributor history lookup, editable Search/Type/Triage/
VM team attribution, bordered Excel reports and native PivotTables. Routine runs
make no AI calls. Windows must remain awake, online and signed in for scheduled runs.

## Install and update

Download `TitleVision-Report-Desk-Setup.exe` from this repository's latest release.
Requires Windows 10/11 x64 and Microsoft Edge. Python/Node and report libraries are
included. Save the TitleVision login and verify a report before enabling 08:45 AM
India-time collection on weekdays. Monday collects Friday through Sunday; Tuesday
through Friday collect the previous calendar day. Manual runs accept a completed
date range of up to 31 days.

## Main monthly workbook

### Automatic monthly workbooks from September 2026

Version 1.4.7 also enables the full monthly refresh for September 2026, so manual
September 1–10 test runs can use the same workflow. Every verified manual or
scheduled run is added automatically. New data for a previously collected date
replaces that date's snapshot, while separate errors on repeated orders remain.
An inclusive range crossing a month boundary updates each matching workbook.

After daily collection, the app downloads all errors created from the month's
first day through the latest completed day and reconciles the export against the
site. Existing rows receive their latest status, points and Last Updated
Date, plus the investigation/client decision and comment columns, matched by the native TitleVision error ID and checked against order/date.
Repeated order numbers and different errors on the same date stay separate.
Non-chargeable points are copied exactly from the source. Unknown or missing
identities stop monthly publication; the previous workbook remains downloadable.

Every run rechecks the affected month before adding its dates and rebuilding all
PivotTables. Earlier published months containing disputed errors are also rechecked
on future runs, including across a month boundary. The separate Refresh status
button still permits a manual check. Create monthly workbook starts an empty
month; Delete workbook removes its published entry and included dates while
retaining daily reports and internal revisions for recovery.
Successful revisions publish atomically after validation. Download the latest
main Excel from the app; already-downloaded copies do not update themselves.
If a monthly update fails, its verified daily report remains downloadable and
the pending Main-workbook addition is retried after a later run.

### Investigation and client replies (v1.4.3)

New collections read each non-New error's Status popup and verify its native error
ID, order, vendor and current status. The source vendor user list separates our
comments from client replies; stored dates/authors allow chronological selection.
The four existing columns are populated without changing the workbook layout:

- **Inv Status / Inv Comments:** Disputed and our latest reply for disputed errors.
  For final Chargeable/Non-Chargeable errors with a vendor reply, the confirmed
  reporting convention retains Disputed and the vendor reply preceding the client
  reply. Accepted/Auto-Accepted retain their exact site status and vendor comment.
- **Client final Status / Client Final Comments:** the source Chargeable or
  Non-Chargeable status and latest external/client reply. Pending disputes have
  no final client decision. No reply means a blank comment, never invented text.

For example, our dispute followed by brucec's “Training, reason accepted” response
on a Non-Chargeable error produces Disputed / our comment / Non-Chargeable / that
reply. Status is copied from TitleVision, not inferred from comment wording.
Month-to-date refresh also updates these four columns, even when only the
comment changed. A missing/conflicting history stops publication and retains the
previous workbook. Older daily downloads stay as saved; recollect their dates to
obtain comments. Download the latest monthly workbook after a refresh.

After a verified report completes, its dates are added without a choice.
The **Main monthly workbook** panel has one download per month; all collected records
continue in the same detail sheet, with the existing summary PivotTables and formulas.

Every error row is preserved, even when an order number repeats on the same day or
on different days. Adding a newer collection for an already-collected Created Date
replaces that date's full snapshot, without changing other dates. Repeating a run
does not duplicate records. Ranges spanning two months update the matching monthly files.

### Save reviewed contributor edits (v1.4.5)

For September 2026 and later months, download the latest Main workbook, change Team,
Searcher, Typer or Final Error Contributor in Excel, and save the file. In the app,
click **Save Excel edits** beside that month and select the saved `.xlsx`.
The confirmation means the corrections are stored locally and included in future
refreshes, daily additions and re-collections of that error. Different errors on
the same order remain separate. TitleVision statuses, points and client comments
continue updating from their verified source.

The Main table contains a hidden error-ID column that moves with a full table
sort. Keep every original row and column; filter rather than delete records.
Source dates and order details cannot be changed through this import. A typed
final contributor is retained for the selected team; changing Team selects the
other team's contributor. All four PivotTables rebuild after a successful save.
Older copies without error IDs require Refresh status and a fresh Main download
before editing. A conflicting edit from an older copy is rejected instead of
overwriting a newer correction; nonconflicting edits preserve newly added rows.

Excel Save alone does not send changes to the app. Use Save Excel edits before
relying on them in a future download, then download the latest Main workbook.
Corrections and the new workbook publish together only after validation. A failed
save leaves both the previous workbook and its saved corrections intact. Removing
a monthly workbook retains corrections for recovery if those error IDs are collected
again. Copies on another PC use that PC's own local application data.

The **Application updates** panel shows the running version. **Get update** checks
the latest stable GitHub release, verifies GitHub's SHA-256 digest, installs it and
restarts the app. It refuses updates while a report is active. Settings, encrypted
credentials, private display-name mappings and reports are stored separately from
versioned application files. Activation keeps the previous version for rollback.
Activation failures show the specific reason. Each attempt saves its result, and
report-engine startup logs are kept under the local data directory's `updates` folder.
Local restart checks bypass HTTP proxy settings. Conflicting services are reported
with their process IDs and are never force-closed by the installer.
The Windows engine owns its socket exclusively, so another copy cannot share its
port. Updates check for conflicting listeners before stopping the previous engine,
then verify the new process using a database-independent readiness endpoint.

For private releases, a PC can reuse Git's existing sign-in as `invicto-labs`, or
use a fine-grained GitHub token with **Contents: read** permission on this repository,
entered under **Private GitHub release access**. A saved read-only token takes priority.
Existing Git credentials are retrieved without prompting and are never copied to app storage.
Do not embed GitHub or TitleVision tokens in source, release files or URLs.

## Publish the next version

1. Make and test the code changes.
2. Bump `version` in `app/version.json` (for example, from `1.2.2` to `1.2.3`).
3. Update `RELEASE_NOTES.md`, commit and push the changes.
4. Create and push the matching tag, e.g. `v1.2.3`.

The release workflow tests the code, builds the Windows installer and publishes a
GitHub release. Installed apps can then receive it through **Get update**. Ordinary
commits do not install themselves on users' computers. Do not reuse a published
version/tag for different files.

## Build locally

On Windows, install Python 3.12 x64, Node.js 24 x64 and Microsoft Edge. Run
`python -m pip install -r requirements.txt` and
`npm install --prefix .build --ignore-scripts playwright@1.62.1`.
Set `TITLEVISION_NODE_EXE` to the installed node.exe and
`TITLEVISION_NODE_MODULES` to `.build/node_modules` (absolute paths). Download the
matching Node license to `app/desktop/licenses/Node-LICENSE.txt`, then run
`python app/desktop/build_full.py`. See the release workflow for exact commands.

The builder outputs installers and a portable ZIP under `outputs`. The old Codex
spreadsheet library is not bundled. Private display-name mappings can be placed
in `%LOCALAPPDATA%\TitleVision Report Desk\data\names.json`; keys are lowercased
username prefixes, values are the desired report names. Existing installations
preserve their mappings during activation. New installations use readable names
derived from the recorded usernames until a mapping is supplied.

## Tests

Run `python app/tests/test_server.py`, `python app/tests/test_updater.py`,
`python app/tests/test_activation.py`,
`python app/tests/test_report.py`, `python app/tests/test_main_workbook.py`, and
`node --test --test-isolation=none app/tests/rules.test.mjs`.

The source repository contains no saved logins, report data, personal display-name
map, installed runtimes or confidential spreadsheet engine. Packaged third-party
components retain their own licenses. The Windows installer is currently unsigned.

### Error statuses

Every run reads and selects all statuses offered by TitleVision. The current set is New, Accepted, Auto-Accepted, Disputed, Non-Chargeable and Chargeable. Reports and monthly refreshes preserve the exact source status and actual points; PivotTables group all statuses present in the included records. Future site statuses are included automatically.
