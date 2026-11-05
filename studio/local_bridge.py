"""Server-owned pending export and authenticated review return.

Pin is supplied by owner-installed, independently reviewed package configuration.
No web request can choose a key, expected hash, run or stage after export.
"""
import hashlib,json,secrets,time,threading
from import_adapter import pending,accept,Refused
class Bridge:
 def __init__(self,pinned_key,expires_at=None):
  if not isinstance(pinned_key,dict):raise Refused('Pinned reviewer key unavailable')
  self.key=dict(pinned_key);self.entries={};self.lock=threading.RLock();self.session=secrets.token_hex(32);self.expires=min(time.time()+1800,expires_at if expires_at is not None else time.time()+1800)
 def export(self,run_id,stage,payload,binding):
  with self.lock:
   now=time.time();self.entries={k:v for k,v in self.entries.items() if now<v['expires']}
   if len(self.entries)>=8:raise Refused('Pending review limit reached')
   session=self.session
   if now>=self.expires:raise Refused('Pairing expired; restart Studio to re-pair')
   p=pending(session,run_id,stage,payload,binding)
   key=stage+':'+p.request_sha256
   if key in self.entries:raise Refused('Exact review already pending or consumed')
   self.entries[key]={'pending':p,'expires':self.expires}
   return {'session':session,'run_id':run_id,'stage':stage,'request_sha256':p.request_sha256,'expires_at':int(self.expires),'reviewer_key_sha256':hashlib.sha256(json.dumps(self.key,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
 def receive(self,session,envelope,root,recompute):
  with self.lock:
   if session!=self.session:raise Refused('Pairing session differs')
   request_hash=envelope.get('record',{}).get('request_sha256')
   entry=self.entries.get(str(envelope.get('record',{}).get('stage'))+':'+str(request_hash))
   if not entry or time.time()>=entry['expires']:raise Refused('Local review session unavailable or expired')
   p=entry['pending']
   # Recompute from authoritative live bytes, never browser supplied expected data.
   payload,binding=recompute(p.run_id,p.stage)
   if hashlib.sha256(payload).hexdigest()!=p.request_sha256:raise Refused('Exact export bytes changed; review refused')
   return accept(p,envelope['record'],envelope['signature'],self.key,root,binding)
