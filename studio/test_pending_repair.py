import pathlib,sys,json
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).parent.parent))
from repofuse.pending_repair import prepare_pending,resume_pending
from repofuse.budget import Budget,BudgetExceeded

def fixture(tmp_path):
 root=tmp_path/'run-0123456789abcdef-fusion';(root/'fused_app/vendor').mkdir(parents=True);(root/'fused_app/vendor/x.py').write_text('VALUE=1')
 planning=tmp_path/'run-0123456789abcdef-planning';planning.mkdir();envfile=planning/'envelope.json';envfile.write_text(json.dumps(dict(max_calls=5,max_count_calls=5,max_input_tokens=12000,max_output_tokens=4096,max_total_input_tokens=60000,max_total_output_tokens=20480)))
 b=Budget(str(planning/'ledger.json'),str(envfile))
 for step in ['idea-suggest','architecture-manifest','glue-synthesis']:b.record_count(step);b.reserve(step,10,100);b.commit(step,{'prompt_tokens':10,'completion_tokens':10})
 env={'MODEL_API_KEY':'test-only-fixture-key'};binding=prepare_pending(root,b,{'integration.py':'def broken(:'},'SyntaxError fixture',{'conflicts':[]},{},'fixture',env,str(envfile));ack=tmp_path/'review.json';ack.write_text(json.dumps(dict(binding=binding,approved=True,reviewer='OFFLINE FIXTURE NOT REAL REVIEW',execution_approved=False)));return root,b,env,ack

def test_pause_no_extra_call_or_secret_export(tmp_path):
 root,b,env,ack=fixture(tmp_path);assert len(b.state['calls'])==3;assert len(b.state['count_calls'])==3
 assert 'test-only-fixture-key' not in (root/'EXACT-repair-NOT-SENT.json').read_text();assert not (root/'repair-resume-attempt.json').exists()
@pytest.mark.parametrize('change',['key','ledger','tree','review','expiry'])
def test_changed_state_before_any_request(tmp_path,monkeypatch,change):
 root,b,env,ack=fixture(tmp_path)
 from repofuse import synthesize
 calls=[];monkeypatch.setattr(synthesize,'call_gated',lambda *a,**k:calls.append(1))
 if change=='key':env['MODEL_API_KEY']='different'
 if change=='ledger':pathlib.Path(b.path).write_text('{}')
 if change=='tree':(root/'fused_app/vendor/x.py').write_text('CHANGED=1')
 if change=='review':ack.write_text('{}')
 if change=='expiry':
  s=json.loads((root/'pending-repair.json').read_text());s['expires_at']=0;(root/'pending-repair.json').write_text(json.dumps(s))
 with pytest.raises((BudgetExceeded,ValueError,KeyError,TypeError)):resume_pending(root,ack,env)
 assert not calls

def test_failed_repair_no_retry(tmp_path,monkeypatch):
 root,b,env,ack=fixture(tmp_path)
 from repofuse import synthesize
 calls=[]
 def bad(*a,**k):calls.append(a[0]);raise BudgetExceeded('fixture transport uncertainty')
 monkeypatch.setattr(synthesize,'call_gated',bad)
 with pytest.raises(BudgetExceeded):resume_pending(root,ack,env)
 with pytest.raises(FileExistsError):resume_pending(root,ack,env)
 assert calls==['syntax-repair']
