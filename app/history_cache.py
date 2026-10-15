"""Reuse comment histories only from successfully reconciled source snapshots."""
from pathlib import Path
from datetime import datetime
import hashlib,json,uuid
from status_history import fields

NAME='status-history-cache.json'

def verified(folder):
    raw=(folder/'source.json').read_bytes()
    receipt=json.loads((folder/'reconciled.json').read_text(encoding='utf8'))
    if hashlib.sha256(raw).hexdigest()!=receipt.get('sourceSha256'):
        raise ValueError('Cannot cache unverified status histories')
    rows=json.loads(raw)
    if not isinstance(rows,list) or receipt.get('count')!=len(rows):
        raise ValueError('Status history cache count mismatch')
    return rows

def usable(record):
    if not isinstance(record,dict) or not isinstance(record.get('sourceId'),str) or not record['sourceId'].isdigit():return False
    if not isinstance(record.get('values'),list) or len(record['values'])!=20:return False
    if not isinstance(record.get('url'),str):return False
    try:fields(record,required=bool(record.get('statusHistory')))
    except (ValueError,TypeError,KeyError,AttributeError):return False
    return True

def load(data):
    path=data/NAME
    if path.exists():
        try:
            saved=json.loads(path.read_text(encoding='utf8'))
            if saved.get('schema')!=1 or not isinstance(saved.get('entries'),dict):return {}
            return {key:row for key,row in saved['entries'].items() if usable(row) and row['sourceId']==key}
        except (ValueError,OSError,AttributeError):return {}
    # Upgrade existing installations without reopening every old status popup.
    # Sort verified observations, including Accepted/New, so A -> B -> A cannot
    # reuse an older A history after the more recent B observation.
    snapshots=[]
    for base in ('runs','month-snapshots'):
        for receipt in (data/base).glob('**/reconciled.json'):
            try:
                folder=receipt.parent
                stamp=json.loads((folder/'collection.json').read_text(encoding='utf8'))['collectedAt']
                at=datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()
                snapshots.append((at,str(folder),verified(folder)))
            except (OSError,ValueError,KeyError,TypeError,AttributeError):continue
    entries={}
    for _,__,rows in sorted(snapshots):
        for row in rows:
            if usable(row):entries[row['sourceId']]=row
            elif isinstance(row,dict):entries.pop(row.get('sourceId'),None)
    return entries

def prepare(data,folder):
    path=folder/'previous-status-histories.json'
    path.write_text(json.dumps(load(data),ensure_ascii=False),encoding='utf8')
    return str(path)

def remember(data,folder):
    rows=verified(folder);entries=load(data)
    for row in rows:
        if usable(row):entries[row['sourceId']]=row
        else:entries.pop(row.get('sourceId'),None)
    target=data/NAME;staged=data/(NAME+'.'+uuid.uuid4().hex+'.tmp')
    try:
        staged.write_text(json.dumps({'schema':1,'entries':entries},ensure_ascii=False),encoding='utf8')
        staged.replace(target)
    finally:staged.unlink(missing_ok=True)
