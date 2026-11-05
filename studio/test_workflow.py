from test_local_http import http,RID,s
import json,urllib.request,pathlib

def read():
 host=next(iter(s.LOCAL_HOSTS))
 with urllib.request.urlopen('http://'+host+'/api/workflow/'+RID,timeout=2) as r:return json.load(r)

def test_readiness_never_generates_or_connects(http,monkeypatch):
 post,run,fr=http
 from repofuse import model_api
 monkeypatch.setattr(model_api,'count_tokens',lambda *a,**k:(_ for _ in ()).throw(AssertionError('network forbidden')))
 data=read();assert data['run_id']==RID;assert data['relay']['available'] is False
 assert data['disclosure_review']=='waiting';assert data['model_connected'] is False
 assert data['actions']==[];assert run['status']=='ideas_ready'
 assert list(fr.iterdir())==[fr/'chosen_intent.json']

def test_review_missing_is_waiting_not_resume(http):
 post,run,fr=http;run['status']='awaiting_review'
 data=read();assert data['actions']==[];assert data['source_review']['matched'] is False

def test_ambiguous_attempt_does_not_offer_retry(http):
 post,run,fr=http;planning=fr.parent/(RID+'-planning');planning.mkdir();(planning/'budget.json').write_text('invalid')
 data=read();assert data['actions']==[];assert 'no retry' in data['blocked']

def test_retained_ideas_are_choices_not_approved_builds(http):
 post,run,fr=http;planning=fr.parent/(RID+'-planning');planning.mkdir();(planning/'model-ideas.json').write_text('{"cards":[]}')
 data=read();assert data['actions']==['choose_retained_model_idea'];assert data['input_qualification']['ready'] is True
