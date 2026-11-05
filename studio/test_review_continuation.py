import pytest
from review_continuation import continue_reviewed,Refused,validate_base
RID='run-0123456789abcdef';BASE='http://127.0.0.1:8327'
def flow(states):
 calls=[];st=iter(states)
 def transport(base,path,body=None):
  calls.append((path,body))
  if path.startswith('/api/workflow/'):return dict(run_id=RID,**next(st))
  if path.endswith('/verify'):return {'status':'build_verified'}
  if path.endswith('/serve'):return {'url':'http://127.0.0.1:40001/'}
  pytest.fail('Unapproved path '+path)
 return calls,transport

def test_wait_then_review_verify_serve_once():
 calls,t=flow([{'status':'awaiting_review','actions':[]},{'status':'awaiting_review','actions':['verify_reviewed_bytes']},{'status':'build_verified','actions':['check_and_serve_reviewed_app']}])
 r=continue_reviewed(BASE,RID,transport=t,sleep=lambda _:None)
 assert r['status']=='served_reviewed_backend';assert r['browser_acceptance']=='not_run'
 assert len([p for p,b in calls if p.endswith('/verify')])==1
 assert len([p for p,b in calls if p.endswith('/serve')])==1
 assert all(p.startswith('/api/workflow/') or p in ['/api/build-general/verify','/api/build-general/serve'] for p,b in calls)

def test_no_approval_or_provider_routes():
 calls,t=flow([{'status':'build_verified','actions':['check_and_serve_reviewed_app']}]);continue_reviewed(BASE,RID,transport=t)
 assert len(calls)==2;assert not any('import' in p or 'generate' in p or 'planning' in p for p,b in calls)

def test_refusal_is_not_retried():
 calls=[]
 def t(*args):calls.append(args);raise Refused('gate refused')
 with pytest.raises(Refused):continue_reviewed(BASE,RID,transport=t)
 assert len(calls)==1

def test_bad_run_and_remote_bases_no_requests():
 for b in ['https://example.com','http://127.0.0.1:8327@evil.test','http://127.0.0.1:8327/path','file:///tmp/a','http://localhost:8327/?x=1']:
  with pytest.raises(Refused):continue_reviewed(b,RID,transport=lambda *a:pytest.fail('no request'))
 with pytest.raises(Refused):continue_reviewed(BASE,'bad',transport=lambda *a:pytest.fail('no request'))

def test_failed_run_stops():
 for state in ['frontend_preflight_failed','build_failed','failed','stopped_safety_blocked','ideas_ready']:
  calls,t=flow([{'status':state,'actions':[]}])
  with pytest.raises(Refused):continue_reviewed(BASE,RID,transport=t)
  assert len(calls)==1

def test_timeout_no_mutations():
 calls,t=flow([{'status':'awaiting_review','actions':[]}]);times=iter([0,0,2])
 with pytest.raises(Refused):continue_reviewed(BASE,RID,timeout=1,transport=t,sleep=lambda _:None,clock=lambda:next(times))
 assert len(calls)==1

def test_wrong_run_refuses():
 with pytest.raises(Refused):continue_reviewed(BASE,RID,transport=lambda *a:{'run_id':'run-ffffffffffffffff','status':'build_verified','actions':['check_and_serve_reviewed_app']})

def test_verify_failure_no_serve():
 calls=[]
 def t(base,path,body=None):
  calls.append(path)
  if path.startswith('/api/workflow/'):return {'run_id':RID,'status':'awaiting_review','actions':['verify_reviewed_bytes']}
  return {'status':'build_failed'}
 with pytest.raises(Refused):continue_reviewed(BASE,RID,transport=t)
 assert not any(p.endswith('/serve') for p in calls)
