"""Cooperative cancellation shared by the desktop and scheduled worker.

Every request names one random operation ID. A delayed Stop request cannot
cancel a later job. The worker lock remains owned until cleanup has finished.
"""
import json,os,threading,uuid
from pathlib import Path

class Cancelled(ValueError):
 def __init__(self):super().__init__('Stopped by you. Previously saved reports and workbook changes were retained.')

_controller=None
def configure(data):
 global _controller
 _controller=Controller(data)
 return _controller

def check_cancelled():
 if _controller:_controller.check()

class Controller:
 def __init__(self,data):
  self.folder=Path(data)/'operations';self.folder.mkdir(parents=True,exist_ok=True)
  self.active=None;self.mutex=threading.RLock()
 def read(self):
  try:
   value=json.loads((self.folder/'active.json').read_text(encoding='utf8'))
   token=value['id']
   if not isinstance(token,str) or len(token)!=32 or any(c not in '0123456789abcdef' for c in token):return None
   return value
  except (OSError,ValueError,KeyError,TypeError):return None
 def marker(self,token):return self.folder/(token+'.cancel')
 def clear_stale(self):
  # Caller owns the worker lock, so a prior descriptor cannot be a live job.
  value=self.read()
  if value:self.end(value['id'])
 def begin(self):
  with self.mutex:
   self.clear_stale()
   token=uuid.uuid4().hex;value={'id':token,'pid':os.getpid()}
   temp=self.folder/(token+'.tmp');temp.write_text(json.dumps(value),encoding='utf8');temp.replace(self.folder/'active.json')
   self.active=token;return token
 def end(self,token):
  with self.mutex:
   if self.active==token:self.active=None
   value=self.read()
   if value and value['id']==token:(self.folder/'active.json').unlink(missing_ok=True)
   self.marker(token).unlink(missing_ok=True)
 def requested(self):
  with self.mutex:return bool(self.active and self.marker(self.active).exists())
 def check(self):
  if self.requested():raise Cancelled()
 def request(self,token):
  with self.mutex:
   value=self.read()
   if not value or value['id']!=token:raise ValueError('That operation has finished. Refresh the page to see the current activity.')
   self.marker(value['id']).touch()
   return {'message':'Stopping the process… Your last saved reports will remain available.','operationId':token}
