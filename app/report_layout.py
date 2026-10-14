"""Keep verified reports from earlier releases readable after the Team column moves."""

LEGACY_HEADERS = [
    'Status', 'Client Order Number', 'TV Order#', 'TraceQ#', 'Client', 'Task',
    'Error Category Type', 'Error Category Sub Type', 'Notes', 'Product',
    'Created Date', 'Region', 'State', 'Points', 'Last Updated Date',
    'Error Committed Date', 'EPON', 'PriceType', 'Searcher', 'QC', 'Typer',
    'Reviewer', 'Team', 'Final Error Contributer', 'Inv Status',
    'Inv Comments', 'Client final Status', 'Client Final Comments',
]
PREVIOUS_HEADERS = LEGACY_HEADERS[:3] + ['Team'] + LEGACY_HEADERS[4:22] + LEGACY_HEADERS[23:]
HEADERS = [h.replace('Contributer','Contributor') for h in PREVIOUS_HEADERS]
TEAMS = ('Search', 'Typing', 'Triage', 'VM Team', 'Leadership')

def normalize_team(value):
    return {'Type': 'Typing', 'VM team': 'VM Team'}.get(value, value)

def normalize_override(override):
    if not override: return None
    return {**override, 'team': normalize_team(override['team']),
            'name': 'VM Team' if override['name'] == 'VM team' else override['name']}

def normalize_values(row):
    row = list(row)
    row[3] = normalize_team(row[3])
    if row[22] == 'VM team': row[22] = 'VM Team'
    return row

def pivot_specs(rows):
    specs = []
    next_row = 3
    for name, field, title, col, preferred in [
        ('ErrorsByContributor',22,'Names',0,3),
        ('ErrorsByStatus',0,'Status',4,3),
        ('ErrorsByTeam',3,'Team',4,11),
        ('ErrorsByPoints',13,'Points',4,19),
    ]:
        items = {r[field] if r[field] is not None else '' for r in rows}
        items = sorted(items, key=lambda v: (v == '', v if isinstance(v,(int,float)) else str(v).casefold()))
        row = max(preferred, next_row) if col else preferred
        specs.append(dict(name=name,field=field,title=title,col=col,row=row,items=items,height=len(items)+2))
        if col: next_row = row + len(items) + 3
    return specs


def current_row(row):
    """Move legacy W Team to D and omit the obsolete TraceQ field."""
    if len(row) == len(HEADERS):
        return list(row)
    if len(row) == len(LEGACY_HEADERS):
        return [*row[:3], row[22], *row[4:22], *row[23:]]
    raise ValueError('Report columns do not match the main workbook.')


def current_rows(headers, rows):
    if headers in (HEADERS, PREVIOUS_HEADERS):
        if any(len(row) != len(HEADERS) for row in rows):
            raise ValueError('Report columns do not match the main workbook.')
        return [normalize_values(row) for row in rows]
    if headers == LEGACY_HEADERS:
        if any(len(row) != len(LEGACY_HEADERS) for row in rows):
            raise ValueError('Report columns do not match the main workbook.')
        return [normalize_values(current_row(row)) for row in rows]
    raise ValueError('Report columns do not match the main workbook.')
