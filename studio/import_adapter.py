"""Signature-authenticated return into original gates. No HTTP/network/provider calls.

PendingReview objects must be created by the local server from its own export,
not reconstructed from browser-supplied expected hashes or reviewer keys.
"""
import dataclasses,hashlib,json,pathlib,tempfile,time
from signed_review import verify,Refused
@dataclasses.dataclass
class PendingReview:
 session:str
 run_id:str
 stage:str
 request_sha256:str
 current_binding:dict
 consumed:bool=False

def pending(session,run_id,stage,request_bytes,current_binding):
 if stage not in ('disclosure','input','source'):raise Refused('Unlisted review stage')
 return PendingReview(session,run_id,stage,hashlib.sha256(request_bytes).hexdigest(),dict(current_binding))

def accept(pending_review,record,signature,pinned_key,studio_root,current_binding,now=None):
 p=pending_review
 if p.consumed:raise Refused('Review already consumed')
 if p.current_binding!=current_binding:raise Refused('Current request changed; re-review required')
 expected={k:getattr(p,k) for k in ('session','run_id','stage','request_sha256')}
 result=verify(record,signature,pinned_key,expected,now)
 if result.get('approved') is not True:raise Refused('Reviewer did not approve this exact stage')
 root=pathlib.Path(studio_root)
 if p.stage=='disclosure':
  import disclosure,review_exchange
  disclosure.check_review(result,current_binding)
  directory=root/'disclosure-acks'
  if root.is_symlink() or directory.is_symlink():raise Refused('Symlink approval directory refused')
  # Fail closed on a crash or disk failure: no replay to guess a write outcome.
  p.consumed=True
  review_exchange._atomic_json(directory/(p.run_id+'.json'),result)
  return {'run_id':p.run_id,'disclosure_imported':True}
 import review_exchange
 if any(result.get(k)!=v for k,v in current_binding.items()):raise Refused('Review result binding differs')
 if p.stage=='source' and not isinstance(result.get('whole_tree'),dict):raise Refused('Whole-source review required')
 if p.stage=='input' and 'whole_tree' in result:raise Refused('Input review cannot approve source')
 # Existing import checks live pins/verdict and every executable byte before write.
 # Temporary record stays under server-owned state, not a browser chosen path.
 if root.is_symlink():raise Refused('Symlink Studio root refused')
 with tempfile.NamedTemporaryFile(mode='w',prefix='.signed-review-',suffix='.json',dir=root,delete=False) as f:
  json.dump(result,f);path=pathlib.Path(f.name)
 try:
  p.consumed=True
  return review_exchange.import_review(path,root)
 finally:path.unlink(missing_ok=True)
