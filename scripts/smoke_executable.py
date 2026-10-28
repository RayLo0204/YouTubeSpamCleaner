"""Exercise the built EXE with no Python or developer tools on its PATH."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request
import uuid


def main():
    parser=argparse.ArgumentParser();parser.add_argument('executable',type=Path)
    parser.add_argument('--mode',choices=['demo','normal'],default='demo')
    args=parser.parse_args();exe=args.executable.resolve()
    root=exe.parent.parent/'artifacts'/('smoke '+args.mode+' '+uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    environment=os.environ.copy()
    environment.pop('PYTHONPATH',None); environment.pop('PYTHONHOME',None)
    environment['PATH']=str(Path(environment.get('SystemRoot','C:/Windows'))/'System32')
    command=[str(exe),'--no-browser','--data-dir',str(root)]
    if args.mode=='demo':command.append('--demo')
    process=subprocess.Popen(command,env=environment,cwd=root,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    result={'mode':args.mode,'executable':exe.name,'developer_tools_removed_from_path':True}
    try:
        end=time.monotonic()+90
        while not (root/'session.json').exists():
            if process.poll() is not None: raise RuntimeError('Executable exited before startup.')
            if time.monotonic()>end: raise TimeoutError('Executable startup timed out.')
            time.sleep(0.1)
        url=json.loads((root/'session.json').read_text(encoding='utf-8'))['url']
        parts=urllib.parse.urlsplit(url);base=urllib.parse.urlunsplit(parts._replace(fragment=''))
        token=urllib.parse.parse_qs(parts.fragment)['session'][0]
        def request(path,body=None):
            data=None if body is None else json.dumps(body).encode()
            req=urllib.request.Request(base+path,data=data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=10) as response:
                raw=response.read()
                return json.loads(raw) if 'application/json' in response.headers.get('Content-Type','') else raw
        def idle():
            end=time.monotonic()+45
            while True:
                state=request('api/state')
                if not state['busy']: return state
                if time.monotonic()>end: raise TimeoutError('Job did not finish.')
                time.sleep(0.1)
        health=request('health');assert health['demo']==(args.mode=='demo')
        assert b'Make room for real conversations.' in request('')
        assert b'function navigate' in request('assets/app.js')
        state=idle()
        if args.mode=='demo':
            assert state['stats']['total']==48
            flagged=request('api/comments?view=flagged')['items'];assert flagged
            ids=[c['id'] for c in flagged[:3]]
            request('api/moderate',{'ids':ids,'action':'hold'})
            state=idle();assert state['jobs'][0]['state']=='completed'
            assert state['stats']['handled']==3
            assert all(a['state']=='confirmed' for a in request('api/actions')['items'])
            request('api/scan',{'max_threads':10,'include_replies':True})
            assert idle()['jobs'][0]['state']=='completed'
            result.update({'sample_comments':48,'simulated_moderation':3,'bounded_rescan':True})
        else:
            assert not state['connected'] and not state['configured'] and state['stats']['total']==0
            request('api/rules',{'kind':'contains','pattern':'example rule'})
            state=request('api/state');assert len(state['rules'])==1
            request('api/oauth/config',{'installed':{'client_id':'test.apps.googleusercontent.com',
                'client_secret':'packaging-test-only','auth_uri':'https://accounts.google.com/o/oauth2/auth',
                'token_uri':'https://oauth2.googleapis.com/token'}})
            assert request('api/state')['configured']
            assert b'packaging-test-only' not in (root/'client.vault').read_bytes()
            assert not (root/'token.vault').exists()
            result.update({'fresh_disconnected_start':True,'rules_without_google_login':True,
                           'bundled_windows_dpapi':True})
        result['csv_export']=b'matched_rules' in request('api/export')
        duplicate=subprocess.run(command,env=environment,cwd=root,timeout=30,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert duplicate.returncode==0 and process.poll() is None
        result['second_launch_reuses_instance']=True
        request('api/shutdown',{})
        assert process.wait(timeout=15)==0
        result['clean_shutdown']=True;result['result']='PASS'
    finally:
        if process.poll() is None:
            process.terminate();process.wait(timeout=10)
    (root/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
