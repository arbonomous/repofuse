"""Bounded local independent-review process orchestration. Disabled unless configured.

The operator supplies an independently reviewed fixed worker script and its hash,
plus trusted public verification key. Repositories/model output cannot select the
worker, key or command. Worker receives source AS UNTRUSTED DATA, no credentials.
Only exact signed affirmative results enter original gates. This supervisor does
not itself review code, sign results, generate, spend, verify or serve an app.
"""
import hashlib,json,os,pathlib,re,secrets,stat,subprocess,sys,tempfile,time,signal
from local_bridge import Bridge
from signed_review import Refused
from review_exchange import RUN_ID,_atomic_json
MAX_REQUEST=16*1024*1024;MAX_RESULT=2*1024*1024

class ReviewService:
 def __init__(self,*,studio_root,worker,worker_sha256,pinned_key,expires_at,timeout=120,python='/usr/bin/python3'):
  self.root=pathlib.Path(studio_root).resolve();self.worker=pathlib.Path(worker);self.worker_hash=worker_sha256;self.python=python;self.timeout=timeout
  if not 1<=timeout<=300 or not self.root.is_dir():raise Refused('Invalid local review service bounds/root')
  if not pathlib.Path(python).is_absolute() or not pathlib.Path(python).is_file():raise Refused('Fixed absolute interpreter required')
  if not re.fullmatch('[0-9a-f]{64}',worker_sha256):raise Refused('Worker hash required')
  self._worker_check();self.bridge=Bridge(pinned_key,expires_at);self.records=self.root/'review-service-records'
  if self.records.is_symlink():raise Refused('Symlink review service state refused')
  self.records.mkdir(mode=0o700,exist_ok=True)
 def _worker_check(self):
  p=self.worker
  if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.stat().st_size>1024*1024 or p.stat().st_mode&0o022:raise Refused('Worker must be fixed regular non-writable-by-others script')
  if hashlib.sha256(p.read_bytes()).hexdigest()!=self.worker_hash:raise Refused('Worker bytes changed')
 def status(self):
  return {'available':time.time()<self.bridge.expires,'scope':'local signed independent worker only','expires_at':int(self.bridge.expires),'automatic_generation':False,'automatic_execution':False}
 def review_once(self,run_id,stage,export):
  if not RUN_ID.fullmatch(run_id) or stage not in ('disclosure','input','source'):raise Refused('Unlisted exact review request')
  # export is owner-installed original stage exporter, never repository supplied.
  payload,binding=export(run_id,stage)
  if not isinstance(payload,bytes) or len(payload)>MAX_REQUEST:raise Refused('Bounded exact request required')
  digest=hashlib.sha256(payload).hexdigest();attempt=self.records/(run_id+'-'+stage+'-'+digest+'.json')
  # O_EXCL records attempt BEFORE launching. Failure, timeout or crash never retries.
  flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY
  try:fd=os.open(attempt,flags,0o600)
  except FileExistsError:raise Refused('Exact request already attempted; no retry')
  with os.fdopen(fd,'w') as f:json.dump({'run_id':run_id,'stage':stage,'request_sha256':digest,'status':'attempted_not_approved'},f)
  receipt=self.bridge.export(run_id,stage,payload,binding);self._worker_check()
  with tempfile.TemporaryDirectory(prefix='repofuse-private-review-') as directory:
   work=pathlib.Path(directory);request=work/'UNTRUSTED-request.bin';context=work/'context.json';result=work/'signed-result.json'
   request.write_bytes(payload);request.chmod(0o400);context.write_text(json.dumps(receipt));context.chmod(0o400)
   worker_copy=work/'trusted-worker.py';worker_bytes=self.worker.read_bytes()
   if hashlib.sha256(worker_bytes).hexdigest()!=self.worker_hash:raise Refused('Worker bytes changed before launch')
   worker_copy.write_bytes(worker_bytes);worker_copy.chmod(0o400)
   # Worker must be a separately trusted reviewer program. No source or model text
   # is interpolated into command. No host credential env is inherited.
   code="import os,resource,sys;resource.setrlimit(resource.RLIMIT_FSIZE,(2097152,2097152));resource.setrlimit(resource.RLIMIT_CPU,(120,120));resource.setrlimit(resource.RLIMIT_NOFILE,(128,128));os.execv(sys.argv[1],sys.argv[1:])"
   env={'PATH':'/usr/bin:/bin','HOME':directory,'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
   child=None
   try:
    child=subprocess.Popen([self.python,'-I','-c',code,self.python,'-I',str(worker_copy),str(request),str(context),str(result)],cwd=directory,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    child.wait(timeout=self.timeout)
   except (OSError,subprocess.TimeoutExpired):raise Refused('Independent worker failed/timed out; no retry')
   finally:
    if child is not None:
     try:os.killpg(child.pid,signal.SIGKILL)
     except ProcessLookupError:pass
     child.wait(timeout=4)
   if child.returncode or not result.exists():raise Refused('Independent worker returned no result; no retry')
   st=result.lstat()
   if not stat.S_ISREG(st.st_mode) or st.st_size>MAX_RESULT:raise Refused('Unbounded or nonregular review response')
   try:envelope=json.loads(result.read_text())
   except (OSError,ValueError):raise Refused('Malformed signed response')
   if not isinstance(envelope,dict) or set(envelope)!={'record','signature'}:raise Refused('Invalid signed response envelope')
   # Re-export exact current bytes AFTER reviewer, before original import.
   imported=self.bridge.receive(receipt['session'],envelope,self.root,export)
  _atomic_json(attempt,{'run_id':run_id,'stage':stage,'request_sha256':digest,'status':'signed_result_imported','result':imported})
  return imported

def original_export(server,run_id,stage):
 """Owner-side adapter. No provider calls, source imports or review shortcuts."""
 if stage=='disclosure':
  _,_,p=server.Handler._planning_prepare(None,run_id)
  from repofuse import model_api
  from disclosure import canonical_payload
  count=canonical_payload(p[1],model_api.build_payload(p[1],max_tokens=1))
  payload=json.dumps({'request_utf8':p[3].decode(),'count_request_utf8':count.decode(),'binding':p[4]},sort_keys=True,separators=(',',':')).encode()
  return payload,p[4]
 with server._lock:
  run=server._runs.get(run_id)
  if not run:raise Refused('Unknown exact retained run')
  run=json.loads(json.dumps(run))
 if stage=='source' and run.get('status') not in ('awaiting_review','frontend_preflight_failed'):raise Refused('No completed source to review')
 from review_exchange import export_bundle,_binding
 payload,_=export_bundle(run,server.RUNS)
 return payload,_binding(run)

def main():
 import argparse,importlib.util,types
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--studio-root',required=True);parser.add_argument('--config',required=True);parser.add_argument('--run-id',required=True);parser.add_argument('--stage',choices=['disclosure','input','source'],required=True);args=parser.parse_args()
 try:
  config_path=pathlib.Path(args.config)
  if config_path.is_symlink() or not config_path.is_file() or config_path.stat().st_size>32000 or config_path.stat().st_mode&0o022:raise Refused('Fixed operator config required')
  config=json.loads(config_path.read_text())
  if set(config)!={'worker','worker_sha256','reviewer_public_key','expires_at','timeout'}:raise Refused('Unlisted operator config fields')
  root=pathlib.Path(args.studio_root)
  if root.is_symlink() or not root.is_dir():raise Refused('Invalid Studio root')
  if not RUN_ID.fullmatch(args.run_id):raise Refused('Invalid exact run id')
  service=ReviewService(studio_root=root,worker=config['worker'],worker_sha256=config['worker_sha256'],pinned_key=config['reviewer_public_key'],expires_at=config['expires_at'],timeout=config['timeout'])
  old=sys.argv;sys.argv=[str(pathlib.Path(__file__).parent/'serve.py')]
  try:
   spec=importlib.util.spec_from_file_location('review_service_owner_studio',pathlib.Path(__file__).parent/'serve.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
  finally:sys.argv=old
  server.ROOT=str(root);server.RUNS=str(root/'runs');server.ACKS=str(root/'safety-acks');server.APPROVALS=str(root/'build-approvals')
  state=root/'runs'/(args.run_id+'-state.json')
  if state.is_symlink() or not state.is_file() or state.stat().st_size>4*1024*1024:raise Refused('Bounded retained state required')
  run=json.loads(state.read_text())
  if run.get('run_id')!=args.run_id:raise Refused('State run id differs')
  server._runs[args.run_id]=run
  result=service.review_once(args.run_id,args.stage,lambda rid,stage:original_export(server,rid,stage))
  print(json.dumps(result))
 except (ValueError,OSError,TypeError,KeyError):parser.exit(1,'Review service refused; no provider call or application execution. Inspect private operator state; no automatic retry.\n')
if __name__=='__main__':main()
