"""Whole HTTP route integration with explicitly inert provider/execution fixtures.

NOT live Meta, network ingest, independent security review or browser proof.
Exercises actual URL guards, planning validation, ledger, synthesis, review
export/import, verify/serve gates and continuation client together.
"""
import importlib.util,io,json,pathlib,sys,threading,time,urllib.request,urllib.error,zipfile
import pytest
HERE=pathlib.Path(__file__).parent;sys.path[:0]=[str(HERE),str(HERE.parent)]
old=sys.argv;sys.argv=['serve.py'];spec=importlib.util.spec_from_file_location('whole_flow_serve',HERE/'serve.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s);sys.argv=old
from repofuse import model_api,gluereview,verify
import model_ideas,review_exchange
from review_continuation import continue_reviewed
A='https://github.com/example/alpha';B='https://github.com/example/beta'
def wait_for(fn):
 end=time.monotonic()+4
 while time.monotonic()<end:
  if fn():return
  time.sleep(.01)
 pytest.fail('fixture state timeout')

@pytest.mark.parametrize('repair',[False,True])
def test_two_inputs_to_gated_open_offline(tmp_path,monkeypatch,repair):
 studio=tmp_path/'studio';runs=studio/'runs';runs.mkdir(parents=True);s._runs.clear();s._active_runs=0;s._local_session=s.LocalSession();s._general_builds.clear()
 for attr,v in [('ROOT',studio),('RUNS',runs),('APPROVALS',studio/'build-approvals'),('ACKS',studio/'safety-acks')]:monkeypatch.setattr(s,attr,str(v))
 def ingest_fixture(rid,a,b,intent):
  assert (a,b)==(A,B)
  with s._lock:
   run=s._runs[rid];run['safety']={'status':'pass','repos':[{'repo':x,'commit':c*40} for x,c in [('alpha','a'),('beta','b')]]};run['events']=[{'data':{'slug':x,'commit':c*40}} for x,c in [('alpha','a'),('beta','b')]]
  metas={x:{'url':u,'slug':x,'commit_sha':c*40,'license_guess':'MIT','tree':[], 'analysis':{'exports':[e],'dependencies':{}}} for x,u,c,e in [('alpha',a,'a','Alpha'),('beta',b,'b','Beta')]}
  planning=runs/(rid+'-planning');planning.mkdir();(planning/'metas.json').write_text(json.dumps(metas))
  fusion=runs/(rid+'-fusion');(fusion/'fused_app/vendor').mkdir(parents=True)
  (fusion/'fused_app/vendor/__init__.py').write_text('# Explicit inert fixture; no real vendor executed.\n')
  manifest={'repos':[{'slug':x,'role':'library','exports':[e],'routes':[],'dependency_count':0} for x,e in [('alpha','Alpha'),('beta','Beta')]],'boundary_candidates':[],'conflicts':[],'acceptance_criteria':[]}
  (fusion/'fuse_manifest.json').write_text(json.dumps(manifest));(fusion/'metas.json').write_text(json.dumps(list(metas.values())))
  with s._lock:run['status']='ideas_ready';s._persist_run_locked(run);s._active_runs-=1
 monkeypatch.setattr(s,'run_pipeline',ingest_fixture)
 calls=[]
 def count(*a,**k):calls.append('count');return 100
 def chat(messages,**kw):
  body=json.loads(messages[1]['content']);task=body.get('task','');calls.append('chat')
  if 'selected_public_repositories' in body:
   rows=body['selected_public_repositories'];c=dict(title='Offline fixture integration',what='Connect alpha and beta',frontend='Browser form',backend='WSGI API',integration='Alpha feeds Beta',runtime='python-wsgi',dependencies=[],external_services=[],risks=['Offline provider fixture, not real generation evidence'],sources=[{'repo':r['repo'],'commit':r['commit'],'exports':r['exports_sample']} for r in rows]);out={'ideas':[c]}
  elif 'architecture bridge manifest' in task:out={'source_exports':{'alpha':['Alpha'],'beta':['Beta']},'arbitrage_opportunity':'Offline fixture','required_shims':[],'bridge':[],'risks':['Offline fixture']}
  elif 'Fix this compiler error once' in task:out={'integration.py':"def describe():\n return {'title':'Repair fixture','description':'Offline only','example':{}}\ndef compute(payload):return payload\n"}
  elif 'Write ONLY integration.py' in task:out={'integration.py':"def describe():\n return {'title':'Offline fixture','description':'Fixture only, no actual model','example':{}}\ndef compute(payload):\n return payload\n"}
  elif 'integration test' in task:out={'test_fused.py':'# Offline fixture only, never executed in this integration test.\n'}
  else:pytest.fail('Unexpected fixture provider task '+task)
  if repair and 'Write ONLY integration.py' in task:out={'integration.py':'def broken(:'}
  return {'content':json.dumps(out),'model':'offline-fixture-NOT-META','usage':{'prompt_tokens':100,'completion_tokens':100},'latency_ms':1,'finish_reason':'stop'}
 monkeypatch.setattr(model_api,'count_tokens',count);monkeypatch.setattr(model_api,'chat_completion',chat)
 executed=[];monkeypatch.setattr(verify,'verify_fused_app',lambda *a,**k:executed.append('mock-backend-verify') or {'status':'passed'})
 server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);port=server.server_address[1];base=f'http://127.0.0.1:{port}';monkeypatch.setattr(s,'LOCAL_HOSTS',{f'127.0.0.1:{port}'});monkeypatch.setattr(s,'LOCAL_ORIGINS',{base});th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
 def post(path,body):
  req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Origin':base,'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=4) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 try:
  assert post('/api/fuse',{'repo_a':A,'repo_b':A})[0]==400
  status,d=post('/api/fuse',{'repo_a':A,'repo_b':B});assert status==200;rid=d['run_id'];wait_for(lambda:s._runs[rid]['status']=='ideas_ready');run=s._runs[rid]
  assert post('/api/local-session/connect',{'key':'fixture-not-real-key'})[0]==200
  assert post('/api/planning/generate',{'run_id':rid,'public_inputs':True,'credit_review':True})[0]==403;assert calls==[]
  root,metas,prepared=s.Handler._planning_prepare(None,rid);ack=studio/'disclosure-acks';ack.mkdir();(ack/(rid+'.json')).write_text(json.dumps(dict(prepared[-1],approved=True,reviewer='EXPLICIT OFFLINE TEST FIXTURE',execution_approved=False)))
  status,result=post('/api/planning/generate',{'run_id':rid,'public_inputs':True,'credit_review':True});assert status==200;assert result['source']=='model:offline-fixture-NOT-META';assert len(result['cards'])==1
  assert post('/api/planning/select',{'run_id':rid,'idea_id':'made-up'})[0]==409
  status,_=post('/api/planning/select',{'run_id':rid,'idea_id':result['cards'][0]['id']});assert status==200
  wait_for(lambda:run['status'] in ['awaiting_review','frontend_preflight_failed','failed','pending_repair_disclosure']);assert executed==[]
  if repair:
   assert run['status']=='pending_repair_disclosure'
   pending=json.loads((runs/(rid+'-fusion')/'pending-repair.json').read_text());review=tmp_path/'dynamic-fixture-review.json';review.write_text(json.dumps({'binding':pending['binding'],'approved':True,'reviewer':'OFFLINE FIXTURE NOT REAL REVIEW','execution_approved':False}))
   from repofuse.pending_repair import resume_pending
   resumed=resume_pending(runs/(rid+'-fusion'),review,{'MODEL_API_KEY':'fixture-not-real-key'})
   assert resumed['status']=='completed'
   s._general_review_or_verify(run,rid)
  assert run['status']=='awaiting_review'
  ledger=json.loads((pathlib.Path(root)/'budget.json').read_text());assert [c['step'] for c in ledger['calls']]==(['idea-suggest','architecture-manifest','glue-synthesis']+(['syntax-repair'] if repair else [])+['test-synthesis']);assert len(calls)==(10 if repair else 8)
  assert post('/api/build-general/serve',{'run_id':rid})[0]==409
  with urllib.request.urlopen(base+'/api/review-package/'+rid) as r:z=zipfile.ZipFile(io.BytesIO(r.read()))
  assert 'fused_app/generated/app.py' in z.namelist();assert not any('budget' in n or 'raw_responses' in n for n in z.namelist())
  app=runs/(rid+'-fusion')/'fused_app';record=dict(review_exchange._binding(run),reviewer='EXPLICIT OFFLINE TEST FIXTURE - NOT AN ACTUAL APPROVAL',whole_tree={'files':{p:gluereview._sha256(str(app/p)) for p in gluereview.review_targets(str(app))}});rp=tmp_path/'review-fixture.json';rp.write_text(json.dumps(record));assert review_exchange.import_review(rp,studio)['whole_tree_imported']
  # Verify/serve gate mechanics only; no generated source execution or real listener.
  monkeypatch.setattr(s,'_spawn_general',lambda *a:(None,40001,None,None))
  out=continue_reviewed(base,rid,timeout=5,poll=1);assert out['url']=='http://127.0.0.1:40001/';assert out['browser_acceptance']=='not_run';assert executed==['mock-backend-verify'];assert len(calls)==(10 if repair else 8)
  assert post('/api/planning/select',{'run_id':rid,'idea_id':result['cards'][0]['id']})[0]==409;assert len(calls)==(10 if repair else 8)
 finally:server.shutdown();server.server_close();th.join();s._general_builds.clear()
