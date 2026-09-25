## Version 1.4.0

Phase 2 activates on 1 October 2026 in India time and applies to October 2026 and later workbooks. September workbooks retain their existing behavior.

- Create a named monthly workbook, refresh its status, or remove it while retaining daily reports for rebuilding. Removing a month clears its approvals; adding daily reports again rebuilds it.
- Keep the Yes/No approval choice. Unapproved daily rows never enter the monthly workbook.
- After a completed daily collection, export and reconcile that month's errors from its first day through the latest completed day. Update approved errors by TitleVision's native error ID, with order and creation-date checks, so repeated order numbers and separate errors remain distinct.
- Copy the latest source status, points and Last Updated Date. Non-chargeable points use the actual site value, including zero; they are not guessed or forced to zero.
- Recheck month-to-date data when adding a report or choosing Refresh status. Build the workbook and all four native PivotTables only after matching and validation pass, then publish the new revision.
- On refresh failure, retain the previous verified workbook, show the failure, and keep the separate daily report available. Missing or conflicting error IDs require review instead of silently dropping rows.
- Show month names, last successful refresh coverage and empty/failed/refreshing states. Existing downloaded Excel copies do not change; download the latest monthly workbook from the app.
- Add October-boundary, duplicate-order, approval, deletion/rebuild, source-integrity and PivotTable regression tests.

Install this release before October 1. The new controls and workflow stay inactive until that date. The October 1 scheduled run still collects September 30; the first scheduled October collection is October 2.

## Version 1.3.5

- Fix Enable schedule failing with “running scripts is disabled” on PCs using the normal Restricted PowerShell policy.
- Launch the bundled schedule script with a process-only execution-policy setting and noninteractive mode. No persistent CurrentUser or LocalMachine policy is changed, and enforced organization policies still take precedence.
- Keep the existing schedule setting when registration or disabling fails, and explain when IT approval is still needed.
- Add a Windows regression that reproduces Restricted policy blocking a harmless script, then verifies the corrected launch succeeds without changing its parent's policy.

On each PC, install this release, save the TitleVision sign-in, complete one verified report, then click Enable schedule. Windows must use India time; keep the user signed in and the PC awake and online.

## Version 1.3.4

- Fix historical errors being blocked when all matching products have since been cancelled and the vendor-side product number differs.
- In that case, choose a product only when exactly one recorded work period overlaps Error Committed Date. Bound the period by both completion and cancellation, preserving date-only precision.
- Keep requiring review for overlapping, missing or invalid dates, and retain exact product-number matching priority.
- Add regression coverage for the September 21 failure, cancellation boundaries and conflicting historical products.

After updating, rerun the failed date. Reports, settings and monthly workbooks are preserved.

## Version 1.3.3

- Resolve repeated products with the same name using Error Committed Date when the product number does not uniquely identify the workflow. Select only when exactly one candidate's recorded arrival/completion period overlaps that date.
- Keep exact product-number matches first, preserve date-only values as a whole day, and never default to the newest product or use the report's creation date to resolve ambiguity.
- Keep requiring review when periods overlap or relevant dates are missing or invalid. Save candidate product details locally for diagnosis.
- Preserve every error row and the existing monthly workbook, contributor formulas and summary PivotTables.

After updating, run the affected date range again. Existing failed runs are retained in history.

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
