"""Publish one editable monthly workbook to a Windows network folder.

Only the designated report PC uses this bridge. SQLite, source evidence and
credentials remain local; an edited shared workbook is imported through the
existing verified manual-edits path before the next monthly rebuild.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import uuid

import main_workbook
import manual_edits


def initialize(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS shared_books (month TEXT PRIMARY KEY, sha256 TEXT NOT NULL)')


def configured(db):
    with db() as c:
        row = c.execute("SELECT value FROM settings WHERE key='shared_folder'").fetchone()
    return json.loads(row[0]) if row else ''


def folder(db):
    name = configured(db)
    if not name:
        return None
    if os.name != 'nt' or not name.startswith('\\\\'):
        raise ValueError('The shared report location must be a Windows network path.')
    location = Path(name)
    if not location.is_dir():
        raise ValueError('The shared report folder is unavailable. Previous shared workbooks were retained.')
    return location


def filename(month):
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('Invalid shared workbook month')
    return f'TitleVision Main Error Report - {month}.xlsx'


def target(db, month):
    location = folder(db)
    return location / filename(month) if location else None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def expected(db, month):
    with db() as c:
        row = c.execute('SELECT sha256 FROM shared_books WHERE month=?', (month,)).fetchone()
    return row['sha256'] if row else None


def remember(db, month, sha256):
    with db() as c:
        c.execute('INSERT OR REPLACE INTO shared_books VALUES (?,?)', (month, sha256))


def closed(path):
    # Excel creates this owner file while a workbook is open on an SMB share.
    if path.with_name('~$' + path.name[2:]).exists():
        raise ValueError(f'{path.name} is open in Excel. Ask the editor to save and close it, then sync again.')


def configure(data, db, path):
    if not isinstance(path, str) or len(path) > 1024 or not path.startswith('\\\\'):
        raise ValueError('Choose a Windows network path beginning with \\\\server\\share.')
    if path.rstrip('\\/') != path:
        path = path.rstrip('\\/')
    place = Path(path)
    if not place.is_dir():
        raise ValueError('The shared folder cannot be reached from this PC.')
    probe = place / ('.titlevision-write-test-' + uuid.uuid4().hex)
    try:
        probe.write_bytes(b'TitleVision write check')
    except OSError as exc:
        raise ValueError('This PC cannot write to the shared folder.') from exc
    finally:
        probe.unlink(missing_ok=True)
    with db() as c:
        months = [row['month'] for row in main_workbook.books(c) if row['month'] >= '2026-09']
    for month in months:
        existing = place / filename(month)
        if existing.exists():
            closed(existing)
            if digest(existing.read_bytes()) != digest(local_book(data, db, month).read_bytes()):
                raise ValueError(f'{existing.name} already exists in the shared folder. Move it aside before enabling this app.')
    with db() as c:
        current = c.execute("SELECT value FROM settings WHERE key='shared_folder'").fetchone()
        if current and json.loads(current[0]) != path:
            raise ValueError('A different shared folder is already configured. Move the existing shared workbooks with IT before changing it.')
        c.execute("INSERT OR REPLACE INTO settings VALUES ('shared_folder',?)", (json.dumps(path),))
    return path


def local_book(data, db, month):
    with db() as c:
        return main_workbook.download(data, c, month)


def pull(root, data, db, run_process, month):
    """Import saved Excel corrections before the report engine changes a month."""
    path = target(db, month)
    if path is None or not path.exists():
        if path is not None and expected(db, month):
            raise ValueError(f'{path.name} is missing from the shared folder. Restore it before refreshing.')
        return None
    closed(path)
    content = path.read_bytes()
    if len(content) > 12 * 1024 * 1024:
        raise ValueError('Shared workbook exceeds the 12 MB edit limit.')
    sha256 = digest(content)
    previous = expected(db, month)
    if previous == sha256:
        return None
    current = local_book(data, db, month)
    if previous is None:
        if digest(current.read_bytes()) != sha256:
            raise ValueError(f'{path.name} already exists and was not published by this app. Review it before enabling sharing.')
        remember(db, month, sha256)
        return None
    result = manual_edits.save(root, data, db, run_process, month, content)
    # The edited shared copy is now the known baseline; a failed publish can be
    # retried without importing the same correction a second time.
    remember(db, month, sha256)
    return result


def publish(data, db, month):
    """Replace the shared copy only if no editor changed it since import."""
    path = target(db, month)
    if path is None:
        return None
    source = local_book(data, db, month)
    check = json.loads((source.parent / 'validation.json').read_text(encoding='utf8'))
    if check.get('passed') is not True:
        raise ValueError('The local Main workbook has not passed validation.')
    new = source.read_bytes()
    previous = expected(db, month)
    if path.exists():
        closed(path)
        actual = digest(path.read_bytes())
        if previous is None and actual != digest(new):
            raise ValueError(f'{path.name} already exists and was not published by this app.')
        if previous is not None and actual != previous:
            raise ValueError(f'{path.name} changed during refresh. The shared copy was retained; sync again.')
    elif previous is not None:
        raise ValueError(f'{path.name} is missing from the shared folder. Restore it before publishing.')
    staged = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        staged.write_bytes(new)
        if digest(staged.read_bytes()) != digest(new):
            raise ValueError('The shared workbook copy failed verification.')
        # A saved edit during staging must never be overwritten.
        if path.exists():
            closed(path)
            if digest(path.read_bytes()) != (previous or digest(new)):
                raise ValueError('The shared workbook changed during publishing. Sync again.')
        from operation_control import check_cancelled
        check_cancelled()
        try:
            staged.replace(path)
        except OSError as exc:
            raise ValueError('Excel or the network share blocked replacing the workbook. Close it and sync again.') from exc
        remember(db, month, digest(new))
        return str(path)
    finally:
        staged.unlink(missing_ok=True)


def sync(root, data, db, run_process, months):
    if not configured(db):
        return []
    months = sorted(set(months))
    for month in months:
        pull(root, data, db, run_process, month)
    return [publish(data, db, month) for month in months]
