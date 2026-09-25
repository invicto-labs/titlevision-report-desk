# TitleVision Report Desk

Windows application for collecting and validating the previous day's TitleVision
error report. It includes contributor history lookup, editable Search/Type/Triage/
VM team attribution, bordered Excel reports and native PivotTables. Routine runs
make no AI calls. Windows must remain awake, online and signed in for scheduled runs.

## Install and update

Download `TitleVision-Report-Desk-Setup.exe` from this repository's latest release.
Requires Windows 10/11 x64 and Microsoft Edge. Python/Node and report libraries are
included. Save the TitleVision login and verify a report before enabling 08:45 AM
India-time collection. Each scheduled run collects the previous calendar day.

## Main monthly workbook

### Phase 2 from October 2026

Version 1.4.0 enables workbook creation, removal and month-to-date status refresh
on 1 October 2026 in India time, for October and later months. September remains
on the existing workflow. The daily schedule still collects the previous calendar
day, so October 1 itself collects September 30.

After daily collection, the app downloads all errors created from the month's
first day through the latest completed day and reconciles the export against the
site. Existing approved rows receive their latest status, points and Last Updated
Date, matched by the native TitleVision error ID and checked against order/date.
Repeated order numbers and different errors on the same date stay separate.
Non-chargeable points are copied exactly from the source. Unknown or missing
identities stop monthly publication; the previous workbook remains downloadable.

The Yes/No choice still controls new daily rows. Choosing Yes rechecks the month
before adding the selected dates and rebuilding all PivotTables. A separate
Refresh status button refreshes already-approved rows. Create monthly workbook
starts an empty month; Delete workbook removes its published entry and approvals,
retains daily reports and internal revisions, and allows reapproval to rebuild it.
Successful revisions publish atomically after validation. Download the latest
main Excel from the app; already-downloaded copies do not update themselves.

After a report completes, choose **Yes, add to main workbook** or **No, keep separate**.
Only approved reports enter the monthly workbook. Scheduled runs also wait for a choice.
The **Main monthly workbook** panel has one download per month; all approved records
continue in the same detail sheet, with the existing summary PivotTables and formulas.

Every error row is preserved, even when an order number repeats on the same day or
on different days. Adding a newer collection for an already-approved Created Date
replaces that date's full snapshot, without changing other dates. Repeating an approval
does not duplicate records. Ranges spanning two months update the matching monthly files.
No leaves the main workbook unchanged; a skipped report can be added later from history.

The app keeps the main workbook locally. Download its latest copy after adding reports.
Changes made in a downloaded Excel copy are not imported into the app. Workbook changes
are published only after validation; a failed update keeps the prior workbook available.

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

Every run reads and selects all statuses offered by TitleVision. The current set is New, Accepted, Auto-Accepted, Disputed, Non-Chargeable and Chargeable. Reports and monthly refreshes preserve the exact source status and actual points; PivotTables group all statuses present in the approved records. Future site statuses are included automatically.
