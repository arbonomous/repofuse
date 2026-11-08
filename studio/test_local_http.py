import importlib.util,json,pathlib,sys,threading,urllib.request,urllib.error
import pytest
HERE=pathlib.Path(__file__).parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
old=sys.argv;sys.argv=['serve.py'];spec=importlib.util.spec_from_file_location('candidate_serve',HERE/'serve.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s);sys.argv=old
RID='run-0123456789abcdef'
@pytest.fixture
def http(tmp_path,monkeypatch):
 s._local_session=s.LocalSession();s._runs.clear();s._active_runs=0
 monkeypatch.setattr(s,'RUNS',str(tmp_path/'runs'));monkeypatch.setattr(s,'ACKS',str(tmp_path/'acks'))
 fr=tmp_path/'runs'/(RID+'-fusion');fr.mkdir(parents=True);(fr/'chosen_intent.json').write_text('{"intent":"selected idea"}')
 s._runs[RID]={'run_id':RID,'events':[{'data':{'slug':'a','commit':'a'*40}}],'status':'ideas_ready','safety':{'status':'pass','repos':[{'repo':'a','commit':'a'*40}]}}
 server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);port=server.server_address[1];base=f'http://127.0.0.1:{port}';monkeypatch.setattr(s,'LOCAL_HOSTS',{f'127.0.0.1:{port}'});monkeypatch.setattr(s,'LOCAL_ORIGINS',{base});thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 def post(path,body,origin=base):
  headers={'Content-Type':'application/json'}
  if origin is not None:headers['Origin']=origin
  req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers=headers)
  try:
   with urllib.request.urlopen(req,timeout=3) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 yield post,s._runs[RID],fr
 server.shutdown();server.server_close();thread.join()

def test_credential_route_exact_origin_and_never_echo(http):
 post,run,fr=http
 for origin in [None,'https://attacker.invalid']:
  status,result=post('/api/local-session/connect',{'key':'fixture-local-key-not-real'},origin);assert status==403;assert not s._local_session.status()['connected']
 status,result=post('/api/local-session/connect',{'key':'fixture-local-key-not-real'});assert status==200;assert 'fixture-local' not in json.dumps(result);assert not list(fr.glob('*key*'))

def test_arm_requires_qualification_no_provider(http):
 post,run,fr=http;post('/api/local-session/connect',{'key':'fixture-local-key-not-real'})
 run['safety']['status']='unknown';status,result=post('/api/local-session/arm',{'run_id':RID,'public_inputs':True,'credit_review':True});assert status==403;assert s._local_session.status()['armed_run'] is None

def test_build_unconnected_or_unarmed_refuses(http):
 post,run,fr=http
 assert post('/api/build-general',{'run_id':RID})[0]==409
 post('/api/local-session/connect',{'key':'fixture-local-key-not-real'})
 assert post('/api/build-general',{'run_id':RID})[0]==409
 assert run['status']=='ideas_ready';assert not (fr/'session-envelope.json').exists()

def test_armed_build_consumed_before_thread(http,monkeypatch):
 post,run,fr=http;post('/api/local-session/connect',{'key':'fixture-local-key-not-real'});assert post('/api/local-session/arm',{'run_id':RID,'public_inputs':True,'credit_review':True})[0]==200
 calls=[]
 monkeypatch.setattr(s,'run_general_build',lambda *args:calls.append(args))
 assert post('/api/build-general',{'run_id':RID})[0]==200
 assert run['status']=='running';assert len(calls)==1;assert calls[0][1]=={'MODEL_API_KEY':'fixture-local-key-not-real'}
 assert post('/api/build-general',{'run_id':RID})[0]==409;assert len(calls)==1
 limits=json.loads((fr/'session-envelope.json').read_text());assert limits['max_calls']==5;assert 'fixture' not in (fr/'session-envelope.json').read_text()

def test_no_http_approval_import_route(http):
 post,run,fr=http;assert post('/api/review-import',{})[0]==404
