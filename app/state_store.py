"""One guarded local database for the desktop, scheduler and backup writer.

The legacy file is a migration source only. A separate durable commit witness
detects rollback/replacement, including a structurally valid older database.
No damaged or regressed database is automatically restored or re-baselined.
"""
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,sqlite3,threading,time,uuid,sys

class StateFault(ValueError):pass

def atomic_json(path,value):
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('w',encoding='utf8') as f:
            json.dump(value,f,sort_keys=True);f.flush();os.fsync(f.fileno())
        temp.replace(path)
    finally:temp.unlink(missing_ok=True)

@contextmanager
def file_lock(path):
    with path.open('a+b') as f:
        deadline=time.monotonic()+30
        while True:
            try:
                f.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>=deadline:raise StateFault('Database writer is busy. Retry after the current save finishes.')
                time.sleep(.05)
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)

def fingerprint(c):
    digest=hashlib.sha256()
    tables=c.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    for name,schema in tables:
        digest.update(json.dumps([name,schema]).encode())
        records=[json.dumps(list(row),ensure_ascii=True,default=lambda v: {'bytes':v.hex()},separators=(',',':')) for row in c.execute('SELECT * FROM "'+name.replace('"','""')+'"')]
        for record in sorted(records):digest.update(record.encode());digest.update(b'\n')
    return digest.hexdigest()

def summary(c):
    tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    result={}
    if 'settings' in tables:
        result['settings']={r[0]:r[1] for r in c.execute("SELECT key,value FROM settings WHERE key IN ('shared_folder','viewer_folder','pc_role','schedule')")}
    for name in ('main_edits','main_days','runs'):
        if name in tables:result[name]=c.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]
    if 'main_books' in tables:result['books']=[list(r) for r in c.execute('SELECT month,count,points FROM main_books ORDER BY month')]
    return result

class Store:
    def __init__(self,data):
        self.data=Path(data).resolve();self.folder=self.data/'state-v2'
        self.folder.mkdir(parents=True,exist_ok=True)
        self.path=self.folder/'reporting.sqlite';self.witness=self.folder/'committed.json'
        self.pending=self.folder/'pending.json';self.fault=self.folder/'repair-required.json'
        self.mutex=threading.RLock();self.local=threading.local()

    def audit(self,event,**values):
        # No employee names, order details, credentials or tokens in this log.
        path=self.folder/'database-events.jsonl'
        if path.exists() and path.stat().st_size>5*1024*1024:
            old=path.with_suffix('.previous.jsonl');path.replace(old)
        with path.open('a',encoding='utf8') as f:
            f.write(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(),pid=os.getpid(),event=event,mode='scheduled' if '--scheduled' in sys.argv else 'desktop',**values))+'\n')
            f.flush();os.fsync(f.fileno())

    def fail(self,reason):
        atomic_json(self.fault,{'reason':reason,'time':datetime.now(timezone.utc).isoformat(),'pid':os.getpid()})
        self.audit('blocked',reason=reason)
        raise StateFault('Report Desk detected a damaged or replaced database and paused changes. Your saved workbooks are retained. Database repair is required. '+reason)

    def file_id(self):
        s=self.path.stat();return [s.st_dev,s.st_ino]

    def read_json(self,path):
        try:return json.loads(path.read_text(encoding='utf8'))
        except (OSError,ValueError):self.fail('The database commit record is missing or unreadable.')

    def migrate(self):
        legacy=self.data/'reporting.sqlite'
        temp=self.folder/'migration.sqlite'
        if temp.exists():self.fail('An interrupted database migration needs review.')
        if legacy.exists():
            source=sqlite3.connect(legacy.as_uri()+'?mode=ro',uri=True)
            try:
                if source.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:self.fail('The legacy database failed verification.')
                current=summary(source)
                # Do not bless the known failure pattern: lost edits and folder.
                settings=current.get('settings',{})
                if settings.get('pc_role')!='"viewer"' and settings.get('shared_folder') in (None,'','""','null'):
                    for backup in (self.data/'database-backups').glob('reporting-*.sqlite'):
                        try:
                            old=sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True)
                            try:prior=summary(old)
                            finally:old.close()
                        except sqlite3.Error:continue
                        if prior.get('settings',{}).get('shared_folder') and prior.get('main_edits',0)>current.get('main_edits',0):
                            self.fail('An earlier backup contains shared configuration and saved edits missing from the current database.')
                destination=sqlite3.connect(temp)
                try:source.backup(destination)
                finally:destination.close()
            finally:source.close()
        else:
            if self.witness.exists() or (self.data/'main').exists() or any((self.data/'database-backups').glob('*.sqlite')):
                self.fail('Existing reports were found without their database; a new empty database was not created.')
            sqlite3.connect(temp).close()
        c=sqlite3.connect(temp)
        try:
            with c:
                c.execute('CREATE TABLE _desk_identity (id TEXT NOT NULL, revision INTEGER NOT NULL)')
                c.execute('INSERT INTO _desk_identity VALUES (?,0)',(uuid.uuid4().hex,))
            if c.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:self.fail('Migrated database failed verification.')
            identity,revision=c.execute('SELECT * FROM _desk_identity').fetchone()
            value={'schema':1,'id':identity,'revision':revision,'digest':fingerprint(c),'summary':summary(c)}
        finally:c.close()
        temp.replace(self.path);value['fileId']=self.file_id();atomic_json(self.witness,value)
        self.audit('migrated',revision=0,digest=value['digest'],summary=value['summary'])

    def validate(self,c):
        witness=self.read_json(self.witness)
        if not isinstance(witness,dict) or not {'digest','fileId','id','revision'}<=witness.keys():self.fail('The database commit record is incomplete.')
        if witness.get('fileId')!=self.file_id():self.fail('The database file was replaced outside the report engine.')
        actual=fingerprint(c)
        if self.pending.exists():
            pending=self.read_json(self.pending)
            if not isinstance(pending,dict) or not isinstance(pending.get('after'),dict) or not {'before','after'}<=pending.keys() or not {'digest','fileId','id','revision'}<=pending['after'].keys():self.fail('The interrupted commit record is incomplete.')
            if actual==pending['after']['digest'] and witness['digest'] in (pending['before'],pending['after']['digest']):
                witness=pending['after'];atomic_json(self.witness,witness)
                self.audit('completed_interrupted_commit',revision=witness['revision'])
            elif actual!=pending['before'] or witness['digest']!=pending['before']:
                self.fail('The database does not match either side of its interrupted commit.')
            self.pending.unlink()
        if actual!=witness['digest']:self.fail('Database contents changed outside a verified commit, or an older state was restored.')
        return witness

    @contextmanager
    def connect(self):
        with self.mutex:
            # Rare nested callers use a savepoint on the same owned connection.
            if getattr(self.local,'connection',None) is not None:
                c=self.local.connection;name='nested_'+uuid.uuid4().hex;c.execute('SAVEPOINT '+name)
                try:yield c;c.execute('RELEASE '+name)
                except BaseException:c.execute('ROLLBACK TO '+name);c.execute('RELEASE '+name);raise
                return
            with file_lock(self.folder/'writer.lock'):
                if self.fault.exists():raise StateFault('Report Desk paused database changes because verification failed. Your saved workbooks are retained. Database repair is required.')
                if not self.path.exists():
                    if self.witness.exists():self.fail('The protected database is missing; legacy data was not substituted.')
                    try:self.migrate()
                    except sqlite3.DatabaseError as error:self.fail('Legacy database migration failed verification: '+str(error))
                c=None
                try:
                    c=sqlite3.connect(self.path,timeout=30);c.row_factory=sqlite3.Row
                    c.execute('PRAGMA synchronous=FULL');c.execute('BEGIN IMMEDIATE')
                    witness=self.validate(c);self.local.connection=c
                    yield c
                    if fingerprint(c)!=witness['digest']:
                        c.execute('UPDATE _desk_identity SET revision=revision+1')
                        identity,revision=c.execute('SELECT * FROM _desk_identity').fetchone()
                        after={'schema':1,'id':identity,'revision':revision,'digest':fingerprint(c),'summary':summary(c),'fileId':self.file_id()}
                        atomic_json(self.pending,{'before':witness['digest'],'after':after})
                        c.commit()
                        atomic_json(self.witness,after);self.pending.unlink()
                        self.audit('commit',revision=revision,digest=after['digest'],summary=after['summary'])
                    else:c.rollback()
                except sqlite3.DatabaseError as error:
                    if c:c.rollback()
                    if (getattr(error,'sqlite_errorcode',0)&255) in (sqlite3.SQLITE_CORRUPT,sqlite3.SQLITE_NOTADB,sqlite3.SQLITE_IOERR):
                        self.fail('SQLite verification failed: '+str(error))
                    raise
                finally:
                    self.local.connection=None
                    if c:c.close()
