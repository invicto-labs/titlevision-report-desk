"""Keep verified reports from earlier releases readable after the Team column moves."""

LEGACY_HEADERS = [
    'Status', 'Client Order Number', 'TV Order#', 'TraceQ#', 'Client', 'Task',
    'Error Category Type', 'Error Category Sub Type', 'Notes', 'Product',
    'Created Date', 'Region', 'State', 'Points', 'Last Updated Date',
    'Error Committed Date', 'EPON', 'PriceType', 'Searcher', 'QC', 'Typer',
    'Reviewer', 'Team', 'Final Error Contributer', 'Inv Status',
    'Inv Comments', 'Client final Status', 'Client Final Comments',
]
HEADERS = LEGACY_HEADERS[:3] + ['Team'] + LEGACY_HEADERS[4:22] + LEGACY_HEADERS[23:]


def current_row(row):
    """Move legacy W Team to D and omit the obsolete TraceQ field."""
    if len(row) == len(HEADERS):
        return list(row)
    if len(row) == len(LEGACY_HEADERS):
        return [*row[:3], row[22], *row[4:22], *row[23:]]
    raise ValueError('Report columns do not match the main workbook.')


def current_rows(headers, rows):
    if headers == HEADERS:
        if any(len(row) != len(HEADERS) for row in rows):
            raise ValueError('Report columns do not match the main workbook.')
        return [list(row) for row in rows]
    if headers == LEGACY_HEADERS:
        if any(len(row) != len(LEGACY_HEADERS) for row in rows):
            raise ValueError('Report columns do not match the main workbook.')
        return [current_row(row) for row in rows]
    raise ValueError('Report columns do not match the main workbook.')
