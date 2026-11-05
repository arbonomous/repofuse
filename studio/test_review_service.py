import hashlib,json,pathlib,sys,time
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from review_service import ReviewService,Refused
RID='run-0123456789abcdef'
# Worker fixtures are NEVER independent reviewer evidence. They refuse/emit invalid data.
def setup(tmp_path,code,timeout=2):
 root=tmp_path/'studio';root.mkdir();worker=tmp_path/'worker.py';worker.write_text(code);worker.chmod(0o600)
 key={'kty':'RSA','alg':'RS256','n':'AA','e':'AQAB'}
 return ReviewService(studio_root=root,worker=worker,worker_sha256=hashlib.sha256(worker.read_bytes()).hexdigest(),pinned_key=key,expires_at=time.time()+60,timeout=timeout),worker

def export(*a):return b'UNTRUSTED DATA ONLY',{'run_id':RID}
def test_missing_result_no_retry(tmp_path):
 s,w=setup(tmp_path,'pass\n')
 with pytest.raises(Refused,match='no result'):s.review_once(RID,'input',export)
 with pytest.raises(Refused,match='already attempted'):s.review_once(RID,'input',export)
 assert not (s.root/'safety-acks').exists()
def test_unsigned_refused(tmp_path):
 s,w=setup(tmp_path,"import pathlib,sys;pathlib.Path(sys.argv[3]).write_text('{\"record\":{},\"signature\":\"\"}')")
 with pytest.raises(Refused):s.review_once(RID,'input',export)
 assert not (s.root/'safety-acks').exists()
def test_changed_worker_refused(tmp_path):
 s,w=setup(tmp_path,'pass\n');w.write_text('print(1)')
 with pytest.raises(Refused,match='changed'):s.review_once(RID,'input',export)
def test_timeout_no_retry(tmp_path):
 s,w=setup(tmp_path,'import time;time.sleep(2)',timeout=1)
 with pytest.raises(Refused,match='timed out'):s.review_once(RID,'input',export)
 with pytest.raises(Refused,match='already attempted'):s.review_once(RID,'input',export)
def test_scrubbed_environment(tmp_path,monkeypatch):
 monkeypatch.setenv('MODEL_API_KEY','fixed-test-marker-not-real')
 s,w=setup(tmp_path,"import os,pathlib,sys;assert 'MODEL_API_KEY' not in os.environ;pathlib.Path(sys.argv[3]).write_text('{}')")
 with pytest.raises(Refused,match='Invalid signed'):s.review_once(RID,'input',export)
def test_symlink_response_refused(tmp_path):
 s,w=setup(tmp_path,"import pathlib,sys;pathlib.Path(sys.argv[3]).symlink_to(sys.argv[2])")
 with pytest.raises(Refused,match='nonregular'):s.review_once(RID,'input',export)
def test_not_available_after_expiry(tmp_path):
 s,w=setup(tmp_path,'pass');s.bridge.expires=time.time()-1
 assert not s.status()['available']
 with pytest.raises(Refused,match='expired'):s.review_once(RID,'input',export)
def test_stage_and_run_constraints(tmp_path):
 s,w=setup(tmp_path,'pass')
 for rid,stage in [('run-no','input'),(RID,'execute')]:
  with pytest.raises(Refused):s.review_once(rid,stage,export)
 assert not list(s.records.iterdir())
@pytest.mark.parametrize('stage',['input','source','disclosure'])
def test_actual_signed_stage_return_original_import(tmp_path,stage):
 # CRYPTOGRAPHIC TEST FIXTURE ONLY, not an actual reviewer decision.
 from cryptography.hazmat.primitives.asymmetric import rsa
 from cryptography.hazmat.primitives import serialization
 import base64,review_exchange
 key=rsa.generate_private_key(public_exponent=65537,key_size=3072);pub=key.public_key().public_numbers()
 enc=lambda n:base64.urlsafe_b64encode(n.to_bytes((n.bit_length()+7)//8,'big')).decode().rstrip('=')
 jwk={'kty':'RSA','alg':'RS256','n':enc(pub.n),'e':enc(pub.e)}
 s,w=setup(tmp_path,'pass')
 run={'run_id':RID,'status':'ideas_ready','events':[{'data':{'slug':'alpha','commit':'a'*40}}],'safety':{'status':'warn','repos':[{'repo':'alpha','commit':'a'*40}]}}
 runs=s.root/'runs';runs.mkdir();(runs/(RID+'-state.json')).write_text(json.dumps(run));binding=review_exchange._binding(run)
 if stage=='source':
  from repofuse import gluereview
  app=runs/(RID+'-fusion')/'fused_app';(app/'generated').mkdir(parents=True);(app/'generated/example.py').write_text('# FIXED CRYPTO TEST SOURCE ONLY\nVALUE=1\n')
  binding=dict(binding,whole_tree={'files':{p:gluereview._sha256(str(app/p)) for p in gluereview.review_targets(str(app))}})
 if stage=='disclosure':binding={'kind':'public-metadata-disclosure-v1','run_id':RID,'payload_sha256':'a'*64,'execution_approved':False}
 # Self-contained stdlib RSA fixture signer. Secret is a test-only generated key,
 # not a credential, never printed or put in deliverable source.
 code="""import pathlib,sys,json,time,hashlib,base64
context=json.loads(pathlib.Path(sys.argv[2]).read_text())
record={k:context[k] for k in ('session','run_id','stage','request_sha256')};record.update(issued_at=int(time.time()),expires_at=int(time.time())+30,result=BINDING)
record['result'].update(approved=True,reviewer='CRYPTO TEST FIXTURE NOT REAL REVIEW')
raw=b'repofuse-private-review-v1\\x00'+json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
digest=bytes.fromhex('3031300d060960864801650304020105000420')+hashlib.sha256(raw).digest();block=b'\\x00\\x01'+b'\\xff'*(384-len(digest)-3)+b'\\x00'+digest
signature=pow(int.from_bytes(block,'big'),PRIVATE_D,MODULUS).to_bytes(384,'big')
pathlib.Path(sys.argv[3]).write_text(json.dumps({'record':record,'signature':base64.b64encode(signature).decode()}))
""".replace('BINDING',repr(binding)).replace('PRIVATE_D',str(key.private_numbers().d)).replace('MODULUS',str(pub.n))
 w.write_text(code);s.worker_hash=hashlib.sha256(w.read_bytes()).hexdigest();s.bridge.key=jwk
 current_binding={k:v for k,v in binding.items() if k!='whole_tree'}
 out=s.review_once(RID,stage,lambda *a:(b'FIXED CRYPTO TEST REQUEST',current_binding))
 if stage=='disclosure':
  assert out['disclosure_imported'];assert not (s.root/'safety-acks').exists();assert not (s.root/'build-approvals').exists()
 else:
  assert out['safety_record_imported'];assert out['whole_tree_imported']==(stage=='source');assert (s.root/'safety-acks'/(RID+'.json')).exists()
 with pytest.raises(Refused):s.review_once(RID,stage,lambda *a:(b'FIXED CRYPTO TEST REQUEST',current_binding))
