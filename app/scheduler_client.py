"""Wake the single desktop engine; never open the report database here."""
import json,subprocess,time,urllib.request,urllib.error
from pathlib import Path

def wake(root,data,port,python):
    origin=f'http://127.0.0.1:{port}'
    http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def state():
        with http.open(origin+'/api/state',timeout=10) as r:return json.load(r)
    try:value=state()
    except urllib.error.HTTPError:raise RuntimeError('The running report engine needs attention. A second database writer was not started.')
    except urllib.error.URLError as error:
        # Only refusal means no server. A timeout or unhealthy server must not
        # launch a replacement which could compete with ongoing work.
        if not isinstance(error.reason,ConnectionRefusedError):raise
        log=Path(data)/'scheduler-startup.log'
        with log.open('ab') as output:
            subprocess.Popen([str(python),str(Path(root)/'server.py')],cwd=root,stdout=output,stderr=output,creationflags=0x08000000)
        for _ in range(60):
            time.sleep(.5)
            try:value=state();break
            except urllib.error.HTTPError:raise RuntimeError('The report engine started but needs database repair.')
            except urllib.error.URLError:continue
        else:raise RuntimeError('The report engine did not start; see scheduler-startup.log.')
    request=urllib.request.Request(origin+'/api/scheduler/wake',b'{}',headers={'Origin':origin,'X-CSRF-Token':value['csrf'],'Content-Type':'application/json'})
    with http.open(request,timeout=30) as response:return json.load(response)
