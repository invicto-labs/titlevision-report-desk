# TitleVision Report Desk

Windows application for collecting and validating the previous day's TitleVision
error report. It includes contributor history lookup, editable Search/Type/Triage/
VM team attribution, bordered Excel reports and native PivotTables. Routine runs
make no AI calls. Windows must remain awake, online and signed in for scheduled runs.

## Install and update

Download `TitleVision-Report-Desk-Setup.exe` from this repository's latest release.
Requires Windows 10/11 x64 and Microsoft Edge. Python/Node and report libraries are
included. Save the TitleVision login and verify a report before enabling 08:45 AM
India-time collection. Each run collects the previous calendar day into a new file.

The **Application updates** panel shows the running version. **Get update** checks
the latest stable GitHub release, verifies GitHub's SHA-256 digest, installs it and
restarts the app. It refuses updates while a report is active. Settings, encrypted
credentials, private display-name mappings and reports are stored separately from
versioned application files. Activation keeps the previous version for rollback.

For private releases, each PC needs a fine-grained GitHub token with **Contents:
read** permission on this repository, entered under **Private GitHub release access**.
Do not embed GitHub or TitleVision tokens in source, release files or URLs.

## Publish the next version

1. Make and test the code changes.
2. Bump `version` in `app/version.json` (for example, from `1.2.0` to `1.2.1`).
3. Update `RELEASE_NOTES.md`, commit and push the changes.
4. Create and push the matching tag, e.g. `v1.2.1`.

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

Run `python app/tests/test_server.py`, `python app/tests/test_updater.py`, and
`node --test --test-isolation=none app/tests/rules.test.mjs`.

The source repository contains no saved logins, report data, personal display-name
map, installed runtimes or confidential spreadsheet engine. Packaged third-party
components retain their own licenses. The Windows installer is currently unsigned.
