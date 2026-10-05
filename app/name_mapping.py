"""Resolve private, role-specific TitleVision usernames to roster names."""
from pathlib import Path
import json,re,uuid


def load(data):
    file=Path(data)/'names.json'
    return json.loads(file.read_text(encoding='utf8')) if file.is_file() else {}


def install(data,raw):
    if not raw or len(raw)>128*1024:raise ValueError('Choose an employee mapping JSON file smaller than 128 KB.')
    try:config=json.loads(raw)
    except (ValueError,UnicodeDecodeError) as error:raise ValueError('Employee mapping must be valid UTF-8 JSON.') from error
    if not isinstance(config,dict) or config.get('schema')!=2:raise ValueError('Choose a version 2 employee mapping file.')
    clean={'schema':2,'search':{},'type':{},'legacy':{}}
    for role in ('search','type'):
        entries=config.get(role)
        if not isinstance(entries,dict) or not entries or len(entries)>1000:raise ValueError(f'Invalid {role} employee aliases.')
        for alias,entry in entries.items():
            if not isinstance(alias,str) or not re.fullmatch(r'[a-z0-9]{1,80}',alias):raise ValueError('An employee alias is invalid.')
            if not isinstance(entry,dict):raise ValueError('An employee entry is invalid.')
            employee_id,name=entry.get('id'),entry.get('name')
            if not isinstance(employee_id,str) or not re.fullmatch(r'[A-Z0-9]{2,20}',employee_id):raise ValueError('An employee ID is invalid.')
            if not isinstance(name,str) or not name.strip() or len(name)>100 or name.lstrip()[0] in '=+-@':raise ValueError('An employee name is invalid.')
            clean[role][alias]={'id':employee_id,'name':name.strip()}
    legacy=config.get('legacy',{})
    if not isinstance(legacy,dict) or len(legacy)>1000:raise ValueError('Invalid previous name aliases.')
    for alias,name in legacy.items():
        if not isinstance(alias,str) or not re.fullmatch(r'[a-z0-9]{1,80}',alias) or not isinstance(name,str) or not name.strip() or len(name)>100 or name.lstrip()[0] in '=+-@':raise ValueError('A previous name alias is invalid.')
        clean['legacy'][alias]=name.strip()
    folder=Path(data);file=folder/'names.json';temp=folder/('names-'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(clean,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        temp.replace(file)
    finally:temp.unlink(missing_ok=True)
    return {'message':'Employee mapping saved. New reports use it automatically; use Refresh status on an existing Main workbook to update its names.','searchAliases':len(clean['search']),'typingAliases':len(clean['type'])}


def summary(data):
    try:
        config=load(data)
        if not isinstance(config,dict):raise ValueError('Invalid employee mapping')
        return {'loaded':config.get('schema')==2,'searchAliases':len(config.get('search',{})),'typingAliases':len(config.get('type',{}))}
    except (ValueError,TypeError,OSError):return {'loaded':False,'searchAliases':0,'typingAliases':0}


def mapped(config,user,role):
    if not user:return None
    prefix=re.sub(r'_ADS.*$','',user,flags=re.I)
    key=re.sub(r'[^a-z0-9]','',prefix.casefold())
    if config.get('schema')==2:
        entry=config.get(role.lower(),{}).get(key)
        if entry is not None:
            name=entry.get('name') if isinstance(entry,dict) else None
            if not isinstance(name,str) or not name.strip():raise ValueError('Invalid employee name mapping')
            return name
        other='type' if role.lower()=='search' else 'search'
        entry=config.get(other,{}).get(key)
        if entry is not None:
            name=entry.get('name') if isinstance(entry,dict) else None
            if not isinstance(name,str) or not name.strip():raise ValueError('Invalid employee name mapping')
            return name
        value=config.get('legacy',{}).get(key)
    else:value=config.get(key)
    return value if isinstance(value,str) and value.strip() else None
