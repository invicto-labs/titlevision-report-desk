"""User-approved monthly workbooks, assembled from complete Created Date snapshots.

Never deduplicate by order number: every source row, including identical errors,
is preserved. Re-collecting a date replaces that date's approved snapshot only.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json, math, re, sys, uuid


def initialize(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS main_choices (run_id TEXT PRIMARY KEY, choice TEXT NOT NULL)')
    connection.execute('CREATE TABLE IF NOT EXISTS main_days (day TEXT PRIMARY KEY, run_id TEXT NOT NULL)')
    connection.execute('CREATE TABLE IF NOT EXISTS main_books (month TEXT PRIMARY KEY, folder TEXT NOT NULL, start TEXT, end TEXT, count INTEGER, points REAL, days INTEGER, updated TEXT)')


def books(connection):
    return [dict(r) for r in connection.execute('SELECT month,start,end,count,points,days,updated FROM main_books ORDER BY month DESC')]


def days_between(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last or (last-first).days > 30:
        raise ValueError('Invalid report date range')
    return [(first+timedelta(days=i)).isoformat() for i in range((last-first).days+1)]


def row_day(row):
    serial = row[10]
    if isinstance(serial, bool) or not isinstance(serial, (int, float)) or not math.isfinite(serial):
        raise ValueError('A report has an invalid Created Date; the main workbook was not changed.')
    return (datetime(1899, 12, 30)+timedelta(days=serial)).date().isoformat()


def load_report(root, data, run):
    folder = data/'runs'/run['id']
    checked = json.loads((folder/'validation.json').read_text(encoding='utf8'))
    if run['status'] not in ('complete', 'review') or checked.get('passed') is not True:
        raise ValueError('Only a verified completed report can be added.')
    payload = json.loads((folder/'payload.json').read_text(encoding='utf8'))
    collection = json.loads((folder/'collection.json').read_text(encoding='utf8'))
    layout = json.loads((root/'templates/layout.json').read_text(encoding='utf8'))
    headers, *rows = payload['data']
    if headers != layout['headers'] or any(len(r) != len(headers) for r in rows):
        raise ValueError('Report columns do not match the main workbook.')
    if collection['start'] != run['start'] or collection['end'] != run['end']:
        raise ValueError('Report dates do not match the verified collection.')
    points = sum(r[13] for r in rows)
    if len(rows) != collection['count'] or points != collection['points'] or len(rows) != run['count'] or points != run['points']:
        raise ValueError('Report totals do not match; the main workbook was not changed.')
    allowed = set(days_between(run['start'], run['end']))
    grouped = {day: [] for day in allowed}
    for row in rows:
        day = row_day(row)
        if day not in allowed:
            raise ValueError('A report row falls outside its Created Date range.')
        grouped[day].append(row)
    return grouped


def make_payload(root, rows):
    layout = json.loads((root/'templates/layout.json').read_text(encoding='utf8'))
    specs = []
    for name, field, title, col, row in [
        ('ErrorsByContributor',23,'Final Error Contributor',0,5),
        ('ErrorsByTeam',22,'Team',4,5),
        ('ErrorsByCategory',6,'Error Category',8,5),
        ('ErrorsByStatus',0,'Status',4,15),
    ]:
        items = {r[field] or '' for r in rows}
        if field in (22,23):
            items.add('VM team')
        items = sorted(items, key=lambda item: (item == '', item.casefold()))
        specs.append(dict(name=name,field=field,title=title,col=col,row=row,items=items,height=len(items)+3))
    return dict(data=[layout['headers'],*rows],specs=specs,tableName='TitleVisionErrors',widths=layout['widths'])


def decide(root, data, db, run_process, rid, add):
    """Called with the application's worker lock held. Publish only after all builds pass."""
    if not re.fullmatch(r'[0-9a-f]{32}', rid) or type(add) is not bool:
        raise ValueError('Invalid main workbook choice')
    with db() as connection:
        found = connection.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
        if not found or found['status'] not in ('complete','review'):
            raise ValueError('Only a verified completed report can be added.')
        run = dict(found)
        prior = connection.execute('SELECT choice FROM main_choices WHERE run_id=?',(rid,)).fetchone()
        if prior and prior['choice'] == 'yes':
            if not add:
                raise ValueError('This report was already added. No does not remove approved records.')
            return {'choice':'yes','books':books(connection),'message':'This report has already been added. No duplicate rows were added.'}
        if not add:
            connection.execute('INSERT OR REPLACE INTO main_choices VALUES (?,?)',(rid,'no'))
            return {'choice':'no','books':books(connection),'message':'Report not added. Your main workbook is unchanged.'}
        selected = dict(connection.execute('SELECT day,run_id FROM main_days').fetchall())
        runs = {r['id']:dict(r) for r in connection.execute('SELECT * FROM runs')}
    incoming = load_report(root,data,run)
    chosen_days = days_between(run['start'],run['end'])
    selected.update({day:rid for day in chosen_days})
    months = sorted({day[:7] for day in chosen_days})
    cache = {rid:incoming}
    revision = uuid.uuid4().hex
    prepared = []
    updated = datetime.now(timezone.utc).isoformat()
    for month in months:
        included = sorted(day for day in selected if day.startswith(month+'-'))
        rows = []
        for day in included:
            source_id = selected[day]
            if source_id not in cache:
                if source_id not in runs:
                    raise ValueError('An approved source report is missing; the main workbook was not changed.')
                cache[source_id] = load_report(root,data,runs[source_id])
            # Append the full daily snapshot. Order numbers are not unique error IDs.
            rows.extend(cache[source_id][day])
        folder = data/'main'/month/revision
        folder.mkdir(parents=True,exist_ok=False)
        points = sum(r[13] for r in rows)
        payload = make_payload(root,rows)
        collection = dict(start=included[0],end=included[-1],count=len(rows),points=points)
        (folder/'payload.json').write_text(json.dumps(payload),encoding='utf8')
        (folder/'collection.json').write_text(json.dumps(collection),encoding='utf8')
        for script in ('build_portable.py','finish.py'):
            run_process([sys.executable,root/'report'/script,folder],folder)
        checked = json.loads((folder/'validation.json').read_text(encoding='utf8'))
        if checked.get('passed') is not True or checked.get('count') != len(rows) or checked.get('points') != points or not (folder/'report.xlsx').is_file():
            raise ValueError('Main workbook validation failed. The previous workbook was retained.')
        prepared.append((month,str(folder.relative_to(data)),included[0],included[-1],len(rows),points,len(included),updated))
    # Atomic pointer changes: failures leave every previous month and decision intact.
    with db() as connection:
        connection.executemany('INSERT OR REPLACE INTO main_books VALUES (?,?,?,?,?,?,?,?)',prepared)
        connection.executemany('INSERT OR REPLACE INTO main_days VALUES (?,?)',[(day,rid) for day in chosen_days])
        connection.execute('INSERT OR REPLACE INTO main_choices VALUES (?,?)',(rid,'yes'))
        result = books(connection)
    return {'choice':'yes','books':result,'message':'Added to the main workbook. Previously added dates in this range were replaced, keeping every error row.'}


def download(data, connection, month):
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('Invalid workbook month')
    found = connection.execute('SELECT folder FROM main_books WHERE month=?',(month,)).fetchone()
    if not found:
        raise ValueError('No main workbook exists for this month yet.')
    file = (data/found['folder']/'report.xlsx').resolve()
    if not file.is_relative_to((data/'main').resolve()):
        raise ValueError('Invalid workbook location')
    return file
