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

def test_operator_review_records_echoed_findings_and_refuses_fail(http,tmp_path,monkeypatch):
 post,run,fr=http
 root=tmp_path/'studio';(root/'runs').mkdir(parents=True)
 monkeypatch.setattr(s,'ROOT',str(root));monkeypatch.setattr(s,'RUNS',str(root/'runs'));monkeypatch.setattr(s,'ACKS',str(root/'safety-acks'))
 run['safety']={'status':'fail','repos':[{'repo':'a','commit':'a'*40,'status':'fail','blocking':True,'static':{'findings':[{'file':'x.py','rule':'dynamic-exec','detail':'exec'}]},'dependencies':{'status':'fail','note':'vuln'}}]}
 status,body=post('/api/operator-review',{'run_id':RID,'stage':'input','reviewer':'Ada','findings':['a|x.py|dynamic-exec|exec']})
 assert status==403 and 'fail' in body['error']
 assert not (root/'safety-acks').exists()
 run['safety']={'status':'warn','repos':[{'repo':'a','commit':'a'*40,'status':'warn','blocking':False,'static':{'findings':[{'file':'x.py','rule':'dynamic-exec','detail':'exec'}]},'dependencies':{'status':'warn','note':'empty'}}]}
 (root/'runs'/(RID+'-state.json')).write_text(json.dumps(run))
 status,body=post('/api/operator-review',{'run_id':RID,'stage':'input','reviewer':'Ada','findings':['forged']})
 assert status==403 and not (root/'safety-acks').exists()
 status,body=post('/api/operator-review',{'run_id':RID,'stage':'input','reviewer':'A','findings':['a|advisory|warn|empty','a|x.py|dynamic-exec|exec']})
 assert status==403
 status,body=post('/api/operator-review',{'run_id':RID,'stage':'input','reviewer':'Ada','findings':['a|advisory|warn|empty','a|x.py|dynamic-exec|exec']})
 assert status==200 and body['safety_record_imported'] is True and body['whole_tree_imported'] is False
 ack=json.loads((root/'safety-acks'/(RID+'.json')).read_text())
 assert ack['reviewer']=='Ada' and ack['run_id']==RID
 ok,why=s.spend_safety_gate(run);assert ok,why
 status,body=post('/api/operator-review',{'run_id':RID,'stage':'input','reviewer':'Ada','findings':['a|advisory|warn|empty','a|x.py|dynamic-exec|exec']},origin='https://attacker.invalid')
 assert status==403

def test_operator_review_source_uses_server_hashes(http,tmp_path,monkeypatch):
 import hashlib
 from repofuse import gluereview
 import operator_review
 post,run,fr=http
 root=tmp_path/'studio';app=root/'runs'/(RID+'-fusion')/'fused_app'
 (app/'generated').mkdir(parents=True)
 (app/'generated'/'integration.py').write_text('def compute(payload):\n    return {}\n')
 (app/'test_fused.py').write_text('def test_ok():\n    assert True\n')
 (app/'serving.json').write_text('{}\n')
 monkeypatch.setattr(s,'ROOT',str(root));monkeypatch.setattr(s,'RUNS',str(root/'runs'));monkeypatch.setattr(s,'ACKS',str(root/'safety-acks'));monkeypatch.setattr(s,'APPROVALS',str(root/'build-approvals'))
 run['status']='awaiting_review'
 run['safety']={'status':'warn','repos':[{'repo':'a','commit':'a'*40,'status':'warn','blocking':False,'static':{'findings':[]},'dependencies':{'status':'warn','note':'empty'}}]}
 (root/'runs'/(RID+'-state.json')).write_text(json.dumps(run))
 files={rel:gluereview._sha256(str(app/rel)) for rel in gluereview.review_targets(str(app))}
 digest=operator_review.tree_digest(files)
 status,body=post('/api/operator-review',{'run_id':RID,'stage':'source','reviewer':'Ada','tree_sha256':'0'*64,'files':{'generated/integration.py':'deadbeef'}})
 assert status==403 and not (root/'build-approvals').exists()
 status,body=post('/api/operator-review',{'run_id':RID,'stage':'source','reviewer':'Ada','tree_sha256':digest,'files':{'generated/integration.py':'deadbeef'}})
 assert status==200 and body['whole_tree_imported'] is True
 written=json.loads((root/'build-approvals'/(RID+'-general.json')).read_text())
 assert written['files']==files and written['files']['generated/integration.py']==hashlib.sha256((app/'generated'/'integration.py').read_bytes()).hexdigest()

def test_planning_generate_checks_safety_before_arm(http,tmp_path,monkeypatch):
 import disclosure
 post,run,fr=http
 post('/api/local-session/connect',{'key':'fixture-local-key-not-real'})
 root=tmp_path/'studio';(root/'disclosure-acks').mkdir(parents=True)
 (root/'disclosure-acks'/(RID+'.json')).write_text('{}')
 monkeypatch.setattr(s,'ROOT',str(root))
 monkeypatch.setattr(s.Handler,'_planning_prepare',lambda self,rid:(str(root),[],({},{},{},{},{})))
 monkeypatch.setattr(disclosure,'check_review',lambda *a,**k:True)
 run['safety']['status']='fail'
 status,body=post('/api/planning/generate',{'run_id':RID,'public_inputs':True,'credit_review':True})
 assert status==403 and 'safety gate' in body['error']
 assert s._local_session.status()['armed_run'] is None
 assert not (root/'session-envelope.json').exists() and not (fr/'session-envelope.json').exists()
