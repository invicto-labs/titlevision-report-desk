## Version 1.3.2

- Prevent multiple Windows report engines from sharing the same address and port by using exclusive socket ownership.
- Detect conflicting listeners before stopping the existing app during an update. Report their process IDs without stopping unrelated services.
- Verify restart readiness through a small, database-independent health endpoint, requiring the exact expected version and process ID.
- Include the observed version/process or connection error when readiness fails, instead of inferring a startup failure from the log banner.
- Allow a short interval for the previous engine's connections to close before rebinding the port.
- Add Windows duplicate-listener, immediate-restart and readiness regressions.

An older duplicate service already running on a PC must be identified and closed once before upgrading. This release prevents new Report Desk copies from sharing its port.

## Activation diagnostics (1.3.1)

- Show the actual activation failure in both Get update and the manual installer, instead of overwriting it with a generic message.
- Keep a separate result for each activation attempt and capture Python startup errors.
- Use direct local health checks that bypass network proxy settings.
- Preserve the original failure reason and still try to restart the old app if restoring its schedule fails.
- Report conflicting listener process IDs while retaining the guard against stopping unrelated services.
- Add installer error-propagation, proxy and rollback regression tests.

This release preserves reports, monthly workbooks and settings. It does not force-close unrelated services using port 8765.

## Main monthly workbook (1.3.0)

- Ask Yes or No before adding a completed report to the main monthly workbook.
- Keep approved dates together in one detail sheet with the existing contributor formulas, borders and native summary PivotTables.
- Preserve every error row, including multiple errors for the same order on the same day or on different days.
- Replace previously approved dates when a new collection of those dates is added. Repeating the same approval never adds duplicate rows.
- Keep separate monthly workbooks when an approved range crosses a month boundary.
- Publish workbook changes only after validation; failed builds keep the previous workbook intact.
- Keep No decisions and pending scheduled reports out of the main workbook. Individual reports remain available.

Download the latest main workbook from its month in the app. Edits made to downloaded copies are not imported back into the app.

## Previous workbook and updater fixes (1.2.4)

- Fix Excel's content-repair warning by correcting PivotTable relationships, workbook XML ordering and copied style metadata.
- Correct empty-report PivotTable cache metadata. Preserve native PivotTables, drill-through, borders and editable contributor formulas.
- Make PivotTable blank-item flags match the actual cached values, including repeated categories.
- Rebuild older downloads from their saved, verified data when needed, keeping the original workbook and report history.
- Show update checks, errors and current-version messages beside Get update. Keep the button disabled during checks and reload the dashboard after a version change.
- Add report regression tests and Microsoft's Open XML format validator to release checks.

Saved sign-in details, reports and the daily schedule are preserved.
