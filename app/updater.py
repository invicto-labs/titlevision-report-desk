"""Explicit, checksum-verified GitHub release updates. No background installation."""
from pathlib import Path
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlparse
import hashlib,json,os,re,subprocess,threading,time,uuid
INSTALLER='TitleVision-Report-Desk-Setup.exe'
MAX_DOWNLOAD=200*1024*1024
def version(value):
 if not re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',value):raise ValueError('Invalid release version')
 return tuple(map(int,value.lstrip('v').split('.')))
class Redirects(HTTPRedirectHandler):
 def redirect_request(self,request,fp,code,msg,headers,newurl):
  parsed=urlparse(newurl)
  if parsed.scheme!='https' or parsed.hostname not in {'api.github.com','github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}:raise ValueError('Update redirected outside GitHub')
  result=super().redirect_request(request,fp,code,msg,headers,newurl)
  if parsed.hostname!='api.github.com':result.remove_header('Authorization')
  return result
class Updates:
 def __init__(self,root,data,encrypt):
  self.root=Path(root);self.data=Path(data);self.encrypt=encrypt;self.lock=threading.Lock()
  self.config=json.loads((self.root/'version.json').read_text(encoding='utf8'))
  if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',self.config['repository']):raise ValueError('Invalid update repository')
  version(self.config['version'])
  self.api='https://api.github.com/repos/'+self.config['repository']
  self.opener=build_opener(Redirects())
 def token(self):
  file=self.data/'github-update.dpapi'
  if file.exists():return self.encrypt(file.read_bytes(),True).decode()
  # Reuse an existing owner sign-in through Git's credential interface only.
  # Never prompt, launch login, or save the publishing credential in app data.
  env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
  try:
   result=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\nusername='+self.config['repository'].split('/')[0]+'\n\n',text=True,capture_output=True,env=env,timeout=10,creationflags=0x08000000 if os.name=='nt' else 0,cwd=self.root)
   if result.returncode==0:
    credential=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    if credential.get('username','').casefold()==self.config['repository'].split('/')[0].casefold():return credential.get('password','')
  except (OSError,subprocess.TimeoutExpired):pass
  return ''
 def save_token(self,value):
  file=self.data/'github-update.dpapi'
  if not value:
   file.unlink(missing_ok=True);return
  if len(value)>4096 or any(c.isspace() for c in value):raise ValueError('Invalid GitHub token')
  temp=file.with_suffix('.tmp');temp.write_bytes(self.encrypt(value.encode()));temp.replace(file)
 def status(self):
  try:
   result=json.loads((self.data/'update-status.json').read_text(encoding='utf8'))
   if result.get('phase') in {'downloading','installing'} and time.time()-result.get('time',0)>=1800:
    return {'phase':'failed','message':'The previous update did not finish. You can try Get update again.'}
   return result
  except (OSError,ValueError):return {'phase':'idle'}
 def busy(self):
  s=self.status();return s.get('phase') in {'downloading','installing'} and time.time()-s.get('time',0)<1800
 def write(self,phase,message,**extra):
  temp=self.data/('update-'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps({'phase':phase,'message':message,'time':time.time(),**extra}),encoding='utf8');temp.replace(self.data/'update-status.json')
 def request(self,url,binary=False):
  if not url.startswith(self.api+'/'):raise ValueError('Unexpected update URL')
  headers={'Accept':'application/octet-stream' if binary else 'application/vnd.github+json','User-Agent':'TitleVision-Report-Desk/'+self.config['version'],'X-GitHub-Api-Version':'2022-11-28'}
  token=self.token()
  if token:headers['Authorization']='Bearer '+token
  try:return self.opener.open(Request(url,headers=headers),timeout=30)
  except HTTPError as e:
   if e.code in (401,403,404):raise ValueError('Release unavailable. For a private repository, save a GitHub token with Contents: read access in Settings.') from None
   raise ValueError('GitHub could not provide the update (HTTP '+str(e.code)+').') from None
 def check(self):
  with self.request(self.api+'/releases/latest') as response:
   raw=response.read(1024*1024+1)
  if len(raw)>1024*1024:raise ValueError('Release metadata is too large')
  release=json.loads(raw)
  if release.get('draft') or release.get('prerelease'):raise ValueError('Only stable published releases can be installed')
  latest=release['tag_name'].lstrip('v');newer=version(latest)>version(self.config['version'])
  result={'current':self.config['version'],'latest':latest,'available':newer,'repository':self.config['repository']}
  if newer:
   matches=[a for a in release.get('assets',[]) if a['name']==INSTALLER and a.get('state')=='uploaded']
   if len(matches)!=1:raise ValueError('The release does not include exactly one Windows installer')
   asset=matches[0];digest=asset.get('digest','')
   if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest):raise ValueError('GitHub has not supplied a SHA-256 checksum for this installer')
   if not 0<asset['size']<=MAX_DOWNLOAD:raise ValueError('Installer size is outside the supported limit')
   url=self.api+'/releases/assets/'+str(int(asset['id']))
   result.update(asset=url,size=asset['size'],sha256=digest.split(':')[1].lower())
  return result
 def install(self):
  if not (self.root/'portable.json').exists():raise ValueError('Install the full desktop edition to use Get update')
  if not self.lock.acquire(False):raise ValueError('An update is already being checked')
  try:
   if self.busy():raise ValueError('An update is already in progress')
   release=self.check()
   if not release['available']:return release
   self.write('downloading','Downloading version '+release['latest'],target=release['latest'])
   threading.Thread(target=self.download,args=(release,),daemon=True).start()
   return release
  finally:self.lock.release()
 def download(self,release):
  try:
   directory=self.data/'updates';directory.mkdir(exist_ok=True)
   target=directory/('setup-'+release['latest']+'-'+uuid.uuid4().hex+'.exe');temp=target.with_suffix('.part');digest=hashlib.sha256();size=0
   with self.request(release['asset'],True) as response,open(temp,'xb') as file:
    while chunk:=response.read(1024*1024):
     size+=len(chunk)
     if size>release['size']:raise ValueError('Downloaded installer is larger than its release metadata')
     digest.update(chunk);file.write(chunk)
   if size!=release['size'] or digest.hexdigest()!=release['sha256']:raise ValueError('Installer checksum did not match; nothing was installed')
   temp.replace(target)
   self.write('installing','Installing version '+release['latest']+'. The application will restart.',target=release['latest'])
   subprocess.Popen([str(target),'--apply-update',str(os.getpid()),str(self.root.parent),release['latest']],creationflags=0x08000000 if os.name=='nt' else 0)
  except Exception as error:
   # Never put an authentication token or signed asset URL in user-facing logs.
   self.write('failed',str(error) if isinstance(error,ValueError) else 'Update download failed. Check the network and try again.')
