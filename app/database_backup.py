"""Verified local database snapshots; never replace a live database automatically."""
from datetime import datetime,timezone
import sqlite3,uuid

def create(data):
    folder=data/'database-backups';folder.mkdir(exist_ok=True)
    name='reporting-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.sqlite'
    target=folder/name;temp=target.with_suffix('.tmp')
    try:
        source=sqlite3.connect((data/'reporting.sqlite').as_uri()+'?mode=ro',uri=True,timeout=5)
        try:
            if source.execute('pragma integrity_check').fetchall()!=[('ok',)]:raise ValueError('Database integrity check failed')
            destination=sqlite3.connect(temp)
            try:
                source.backup(destination)
                if destination.execute('pragma integrity_check').fetchall()!=[('ok',)]:raise ValueError('Database backup verification failed')
            finally:destination.close()
        finally:source.close()
        temp.replace(target)
        for old in sorted(folder.glob('reporting-*.sqlite'),reverse=True)[5:]:old.unlink()
        return target
    finally:temp.unlink(missing_ok=True)

def corrupt(error):
    code=getattr(error,'sqlite_errorcode',0)&255
    return code in (sqlite3.SQLITE_CORRUPT,sqlite3.SQLITE_NOTADB) or 'malformed' in str(error).lower()
