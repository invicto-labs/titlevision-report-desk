TITLEVISION REPORT DESK — FULL WINDOWS APPLICATION

Requirements: 64-bit Windows 10 or Windows 11, Microsoft Edge, internet access.
Python, Node.js and the report libraries are included. Codex is not required.

INSTALL
Run TitleVision Report Desk Full Setup.exe. Click Install. Then use the desktop
or Start menu shortcut. No administrator access is needed.
If using the ZIP, select Extract All first, then open TitleVision Report Desk.exe
inside the extracted folder. Keep the entire extracted folder together.

FIRST RUN ON A NEW COMPUTER
1. Save your TitleVision username and password in Settings.
2. Run a report for a completed date and check the result.
3. Enable the daily 08:45 India-time schedule. Windows must use India time.
This collects the previous calendar day. Keep the computer awake, online and
signed into Windows. Turn off the old computer's schedule if only one computer
should collect reports. Schedules and sign-in details are not transferred.

The normal export, every-row verification, correct product history lookup, latest
completed Search/Typing attribution, Triage and VM team handling, editable Team
formulas, full borders and native PivotTables are included. Ambiguous data remains
flagged for review. Site login challenges or layout changes can require action.

The Excel writer uses a portable library; it does not require the original Codex
spreadsheet runtime. Excel is needed to use the workbook interactively, but is not
required for report collection or file generation.

Your new computer stores its own reports, settings and Windows-encrypted sign-in
under %LOCALAPPDATA%\TitleVision Report Desk\data. No saved credentials or old
reports are included in the download. Existing private staff display-name maps
are preserved during updates. New PCs can add their own data\names.json map.

UPDATES
The Application updates panel shows the running version. Get update downloads
and verifies the latest stable GitHub release, then installs it and restarts.
For this private repository, reuse Git's existing sign-in as invicto-labs, or save
a fine-grained token with Contents: read access under Private GitHub release access
on each PC. Never share a write token.
Updates preserve reports, settings and the daily schedule.

If startup fails, double-click Check Application.cmd. It tests the included Python
and Node runtimes and a blank Edge session, without logging into TitleVision.

This installer is a locally built unsigned application. It is for x64 Windows;
other operating systems and processor architectures have not been tested.

REMOVAL
Pause the schedule in Settings first. Delete the desktop and Start menu shortcuts
and the installed version folders under
%LOCALAPPDATA%\Programs\TitleVision Report Desk\versions.
Reports remain under %LOCALAPPDATA%\TitleVision Report Desk\data.
Keep that data directory if you want to retain your reports.

Third-party license notices are included in runtime directories and the licenses
folder. The desktop package includes only the application and redistributable
runtime components; no OpenAI proprietary spreadsheet runtime is included.
