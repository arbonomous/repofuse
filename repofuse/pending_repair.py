"""Durable exact one-shot compiler repair. No request until exact review matches."""
import pathlib,json,hashlib,time,os
from .budget import Budget,BudgetExceeded
from . import model_api

def digest(value):return hashlib.sha256(value).hexdigest()
def regular(path,limit=2*1024*1024):
 p=pathlib.Path(path)
 if p.is_symlink() or not p.is_file() or p.stat().st_size>limit:raise BudgetExceeded('Nonregular/unbounded repair state')
 return p.read_bytes()
def tree_snapshot(root):
 app=root/'fused_app'
 if app.is_symlink() or any(p.is_symlink() for p in app.rglob('*')):raise BudgetExceeded('Symlink execution tree')
 return {p.relative_to(root).as_posix():digest(regular(p,16*1024*1024)) for p in app.rglob('*') if p.is_file()}
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def check_ledger(budget):
 names=['idea-suggest','architecture-manifest','glue-synthesis']
 if [x.get('step') for x in budget.state['calls']]!=names or any(not isinstance(x.get('actual'),dict) for x in budget.state['calls']) or [x.get('step') for x in budget.state.get('count_calls',[])]!=names:raise BudgetExceeded('Repair requires exactly3committed original stages, no repair/testattempt')
 if budget.envelope['max_calls']!=5 or budget.envelope['max_count_calls']!=5:raise BudgetExceeded('Repair requires exact5stage fresh envelope')
def prepare_pending(out_dir,budget,files,error,manifest,architecture,intent,env,envelope_path):
 from .synthesize import build_syntax_repair_prompt,PIPELINE_REASONING_EFFORT,GLUE_RESPONSE_FORMAT
 check_ledger(budget);root=pathlib.Path(out_dir)
 if root.is_symlink():raise BudgetExceeded('Symlink fusionroot')
 messages=build_syntax_repair_prompt(files,error)
 payload=model_api.build_payload(messages,reasoning_effort=PIPELINE_REASONING_EFFORT,response_format=GLUE_RESPONSE_FORMAT)
 count=model_api.build_payload(messages,max_tokens=1)
 binding={'kind':'repofuse-exact-syntax-repair-v1','run_id':root.name.removesuffix('-fusion'),'payload_sha256':digest(json.dumps(payload).encode()),'count_sha256':digest(json.dumps(count).encode()),'ledger_sha256':digest(regular(budget.path)),'envelope_sha256':digest(regular(envelope_path))}
 state={'credential_sha256':digest(model_api._api_key(env).encode()),'binding':binding,'expires_at':int(time.time())+1800,'messages':messages,'files':files,'compiler_error':error,'manifest':manifest,'architecture':architecture,'intent':intent,'ledger':str(pathlib.Path(budget.path).resolve()),'envelope':str(pathlib.Path(envelope_path).resolve()),'status':'pending_repair_disclosure'}
 # Original tree static bytes and metadata bound for resume; no executable files yet.
 state['context_sha256']=digest(canonical({'files':files,'compiler_error':error,'manifest':manifest,'architecture':architecture,'intent':intent}))
 state['tree']=tree_snapshot(root)
 binding['context_sha256']=state['context_sha256'];binding['tree_sha256']=digest(canonical(state['tree']))
 with (root/'pending-repair.json').open('x') as f:json.dump(state,f,indent=2)
 with (root/'EXACT-repair-NOT-SENT.json').open('x') as f:json.dump(payload,f)
 with (root/'EXACT-repair-count-NOT-SENT.json').open('x') as f:json.dump(count,f)
 return binding

def resume_pending(out_dir,review_path,env):
 from .synthesize import call_gated,_extract_json,validate_glue_size,validate_python_outputs,finish_integration,PIPELINE_REASONING_EFFORT,GLUE_RESPONSE_FORMAT
 rawroot=pathlib.Path(out_dir)
 if rawroot.is_symlink():raise BudgetExceeded('Symlink fusionroot')
 root=rawroot.resolve();state=json.loads(regular(root/'pending-repair.json'));binding=state['binding'];review=json.loads(regular(review_path))
 if state['status']!='pending_repair_disclosure' or time.time()>=state['expires_at']:raise BudgetExceeded('Pending repair expired/not resumable')
 if review.get('binding')!=binding or review.get('approved') is not True or not review.get('reviewer') or review.get('execution_approved') is not False:raise BudgetExceeded('Exact independent dynamic repair disclosure review required')
 if digest(canonical({k:state[k] for k in ('files','compiler_error','manifest','architecture','intent')}))!=binding['context_sha256'] or digest(canonical(state['tree']))!=binding['tree_sha256']:raise BudgetExceeded('Pending context changed')
 if pathlib.Path(state['ledger']).parent!=root.parent/(root.name.removesuffix('-fusion')+'-planning') or pathlib.Path(state['envelope']).parent!=pathlib.Path(state['ledger']).parent:raise BudgetExceeded('Repair paths outside original planning directory')
 budget=Budget(state['ledger'],envelope_path=state['envelope']);check_ledger(budget)
 if digest(regular(budget.path))!=binding['ledger_sha256'] or digest(regular(state['envelope']))!=binding['envelope_sha256'] or digest((model_api._api_key(env) or '').encode())!=state['credential_sha256']:raise BudgetExceeded('Ledger/envelope/credential changed')
 tree=tree_snapshot(root)
 if tree!=state['tree']:raise BudgetExceeded('Source tree changed')
 payload=model_api.build_payload(state['messages'],reasoning_effort=PIPELINE_REASONING_EFFORT,response_format=GLUE_RESPONSE_FORMAT);count=model_api.build_payload(state['messages'],max_tokens=1)
 if digest(json.dumps(payload).encode())!=binding['payload_sha256'] or digest(json.dumps(count).encode())!=binding['count_sha256']:raise BudgetExceeded('Exact repair payload changed')
 # Exclusive attempt marker is consumed before any count/network, even crash/failure.
 with (root/'repair-resume-attempt.json').open('x') as f:json.dump({'binding':binding,'status':'attempted_not_approved'},f)
 response,_=call_gated('syntax-repair',state['messages'],str(root),budget,env=env,reasoning_effort=PIPELINE_REASONING_EFFORT,response_format=GLUE_RESPONSE_FORMAT)
 files=_extract_json(response['content']);validate_glue_size(files)
 if set(files)!={'integration.py'}:raise BudgetExceeded('Repair slot differs')
 validate_python_outputs(files)
 with (root/'syntax-repair-provenance.json').open('x') as f:json.dump({'original_sha256':digest(state['files']['integration.py'].encode()),'repaired_sha256':digest(files['integration.py'].encode()),'compiler_error':state['compiler_error'],'execution_approved':False},f,indent=2)
 result={'status':'completed','steps':{'idea-suggest':'retained','architecture-manifest':'retained','glue-synthesis':'retained','syntax-repair':'one exact reviewed repair'},'files_written':[]}
 result=finish_integration(str(root),budget,files,response,state['manifest'],state['architecture'],state['intent'],env,result,time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
 from .serving import derive_contract
 derive_contract(str(root/'fused_app'))
 return result


def main():
 import argparse,sys
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--studio-root',required=True);parser.add_argument('--run-id',required=True);parser.add_argument('--review',required=True);parser.add_argument('--key-file',required=True);args=parser.parse_args()
 keypath=pathlib.Path(args.key_file)
 try:
  root=pathlib.Path(args.studio_root)
  import re
  if root.is_symlink() or not re.fullmatch('run-[0-9a-f]{16}',args.run_id):raise BudgetExceeded('Invalid local root/run')
  sys.path.insert(0,str(pathlib.Path(__file__).parent.parent/'studio'))
  old=sys.argv;sys.argv=['serve.py']
  try:import serve
  finally:sys.argv=old
  serve.ROOT=str(root);serve.RUNS=str(root/'runs');serve.ACKS=str(root/'safety-acks');serve.APPROVALS=str(root/'build-approvals')
  statepath=root/'runs'/(args.run_id+'-state.json');run=json.loads(regular(statepath,4*1024*1024))
  if run.get('run_id')!=args.run_id or run.get('status')!='pending_repair_disclosure':raise BudgetExceeded('Run not pending exact repair')
  safe,why=serve.spend_safety_gate(run)
  if not safe:raise BudgetExceeded('Original input qualification refused: '+why)
  key=regular(keypath,4096).decode().strip();keypath.unlink(missing_ok=True)
  try:result=resume_pending(root/'runs'/(args.run_id+'-fusion'),args.review,{'MODEL_API_KEY':key})
  finally:key=None
  serve._runs[args.run_id]=run
  if result.get('status')=='completed':serve._general_review_or_verify(run,args.run_id)
  with serve._lock:serve._persist_run_locked(run)
  print(json.dumps({'run_id':args.run_id,'status':run['status'],'result':result}))
 except (ValueError,OSError,KeyError,TypeError,BudgetExceeded,model_api.ModelCallError):parser.exit(1,'Repair continuation refused or failed; attempts retained, never retry. No application execution authorized.\n')
 finally:keypath.unlink(missing_ok=True)
if __name__=='__main__':main()
