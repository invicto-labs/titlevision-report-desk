"""Verified local database snapshots; never replace a live database automatically."""
from datetime import datetime,timezone
import sqlite3,uuid

def create(data):
    from contextlib import contextmanager
    import state_store
    folder=data/'database-backups';folder.mkdir(exist_ok=True)
    protected=(data/'state-v2/committed.json').exists() or (data/'state-v2/reporting.sqlite').exists() or (data/'state-v2/repair-required.json').exists()
    @contextmanager
    def source_connection():
        if protected:
            with state_store.Store(data).connect() as c:yield c
        else:
            c=sqlite3.connect((data/'reporting.sqlite').as_uri()+'?mode=ro',uri=True,timeout=5)
            try:yield c
            finally:c.close()
    name=('reporting-v2-' if protected else 'reporting-')+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.sqlite'
    target=folder/name;temp=target.with_suffix('.tmp')
    try:
        with source_connection() as source:
            if [tuple(r) for r in source.execute('pragma integrity_check')]!=[('ok',)]:raise ValueError('Database integrity check failed')
            # The store lock excludes writers. A second read-only connection
            # avoids SQLite backup waiting on this connection's IMMEDIATE tx.
            reader=sqlite3.connect(((data/'state-v2/reporting.sqlite') if protected else data/'reporting.sqlite').as_uri()+'?mode=ro',uri=True)
            destination=sqlite3.connect(temp)
            try:
                reader.backup(destination)
                if destination.execute('pragma integrity_check').fetchall()!=[('ok',)]:raise ValueError('Database backup verification failed')
                if protected and state_store.fingerprint(destination)!=state_store.fingerprint(source):raise ValueError('Backup does not match the verified current state')
            finally:destination.close();reader.close()
            temp.replace(target)
        # Keep ten recent snapshots plus one per day for thirty days. Do not
        # prune legacy evidence; it may be needed to diagnose a prior rollback.
        if protected:
            from datetime import timedelta
            snapshots=sorted(folder.glob('reporting-v2-*.sqlite'),reverse=True)
            keep=set(snapshots[:10]);days=set();cutoff=(datetime.now(timezone.utc)-timedelta(days=30)).strftime('%Y%m%d')
            for file in snapshots:
                day=file.name[len('reporting-v2-'):][:8]
                if day>=cutoff and day not in days:keep.add(file);days.add(day)
            for file in snapshots:
                if file not in keep:file.unlink()
        return target
    finally:temp.unlink(missing_ok=True)


def corrupt(error):
    code=getattr(error,'sqlite_errorcode',0)&255
    return code in (sqlite3.SQLITE_CORRUPT,sqlite3.SQLITE_NOTADB) or 'malformed' in str(error).lower()
