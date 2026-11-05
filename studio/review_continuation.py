"""Bounded local continuation after independently imported exact-byte review.

Never writes an approval, submits source, creates a model request or retries
model work. Uses existing verify/serve routes, which recheck original gates.
An operator starts this for one known local run; it waits for original
workflow readiness, verifies once, then opens/returns the reviewed app URL.
No remote host, custom origin or credential support is provided here.
"""
import argparse,json,re,time,urllib.request,urllib.error,urllib.parse
RUN=re.compile(r'^run-[0-9a-f]{16}$')
class Refused(ValueError):pass

def validate_base(base):
 try:
  u=urllib.parse.urlsplit(base);port=u.port
 except ValueError:raise Refused('Invalid local Studio address')
 if (u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost') or
     not port or not 1<=port<=65535 or u.username or u.password or
     u.path not in ('','/') or u.query or u.fragment):
  raise Refused('Only an explicit local Studio HTTP port is allowed')
 return base.rstrip('/')

def request(base,path,body=None):
 headers={'Origin':base,'Content-Type':'application/json'}
 data=None if body is None else json.dumps(body).encode()
 req=urllib.request.Request(base+path,data=data,headers=headers)
 # Redirects must not turn local requests into remote side effects.
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args):return None
 try:
  with urllib.request.build_opener(NoRedirect).open(req,timeout=120) as r:
   raw=r.read(1024*1024+1)
 except urllib.error.HTTPError as e:raise Refused('Studio refused continuation (HTTP '+str(e.code)+'); no retry')
 if len(raw)>1024*1024:raise Refused('Studio response exceeds bound')
 try:d=json.loads(raw)
 except ValueError:raise Refused('Invalid Studio response')
 if not isinstance(d,dict):raise Refused('Unexpected Studio response')
 if d.get('error'):raise Refused(str(d['error']))
 return d

def continue_reviewed(base,run_id,timeout=1800,poll=5,transport=request,sleep=time.sleep,clock=time.monotonic,on_status=None):
 base=validate_base(base)
 if not RUN.fullmatch(run_id):raise Refused('Invalid retained run id')
 if not 1<=timeout<=7200 or not 1<=poll<=60:raise Refused('Wait bounds invalid')
 start=clock();verified=False;last=None
 while clock()-start<timeout:
  d=transport(base,'/api/workflow/'+run_id)
  if d.get('run_id')!=run_id:raise Refused('Workflow returned a different run')
  status=d.get('status');actions=d.get('actions',[])
  if status!=last:
   if on_status:on_status({'run_id':run_id,'status':status,'browser_acceptance':'not_run'})
   last=status
  if status in ('frontend_preflight_failed','build_failed','failed','stopped_safety_blocked'):
   raise Refused('Run requires independent repair or qualification: '+status)
  if 'verify_reviewed_bytes' in actions:
   if verified:raise Refused('Verification already attempted; not retried')
   # Workflow is only a hint. Original endpoint rechecks safety/exact review.
   verified=True;r=transport(base,'/api/build-general/verify',{'run_id':run_id})
   if r.get('status')!='build_verified':raise Refused('Reviewed backend verification did not pass; no retry')
   continue
  if 'check_and_serve_reviewed_app' in actions:
   r=transport(base,'/api/build-general/serve',{'run_id':run_id});url=r.get('url')
   try:validate_base(url)
   except (TypeError,ValueError):raise Refused('Serve did not return a local reviewed app address')
   return {'run_id':run_id,'status':'served_reviewed_backend','url':url,
           'browser_acceptance':'not_run','note':'Open the URL and test the actual browser flow. This is not full-product or browser acceptance.'}
  if status not in ('awaiting_review','build_verified','running'):
   raise Refused('Run has not reached review continuation: '+str(status))
  sleep(poll)
 raise Refused('Review wait expired; no provider or verification retry requested')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--studio',required=True);p.add_argument('--run-id',required=True);p.add_argument('--timeout',type=int,default=1800)
 a=p.parse_args()
 try:r=continue_reviewed(a.studio,a.run_id,timeout=a.timeout,on_status=lambda d:print(json.dumps(d),flush=True));print(json.dumps(r),flush=True)
 except (Refused,OSError) as e:p.exit(1,'Continuation stopped: '+str(e)+'\n')
if __name__=='__main__':main()
