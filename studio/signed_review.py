"""Detached RSA SHA-256 review verification. No signing key or effects."""
import base64,hashlib,json,time
DOMAIN=b'repofuse-private-review-v1\x00'
DIGESTINFO=bytes.fromhex('3031300d060960864801650304020105000420')
class Refused(ValueError):pass
def canonical(record):
 return DOMAIN+json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def decode(value):
 try:return base64.b64decode(value,validate=True)
 except (ValueError,TypeError):raise Refused('Invalid base64')
def verify(record,signature,key,expected,now=None):
 if not isinstance(record,dict) or set(record)!={'session','run_id','stage','request_sha256','result','expires_at','issued_at'}:raise Refused('Invalid review envelope')
 for field in ('session','run_id','stage','request_sha256'):
  if record.get(field)!=expected.get(field):raise Refused('Review binding differs')
 now=time.time() if now is None else now
 issued=record['issued_at'];expires=record['expires_at']
 if any(type(x) is not int for x in (issued,expires)) or not issued<=now<expires or expires-issued>1800:raise Refused('Review expired or time bounds invalid')
 if not isinstance(record['result'],dict):raise Refused('Invalid review result')
 if not isinstance(key,dict) or key.get('kty')!='RSA' or key.get('alg')!='RS256':raise Refused('Unlisted review key')
 try:
  n=int.from_bytes(base64.urlsafe_b64decode(key['n']+'='*(-len(key['n'])%4)),'big');e=int.from_bytes(base64.urlsafe_b64decode(key['e']+'='*(-len(key['e'])%4)),'big')
 except Exception:raise Refused('Invalid RSA key')
 if n.bit_length()!=3072 or e!=65537:raise Refused('Unlisted RSA parameters')
 sig=decode(signature);width=(n.bit_length()+7)//8
 if len(sig)!=width or int.from_bytes(sig,'big')>=n:raise Refused('Invalid signature size')
 digest=DIGESTINFO+hashlib.sha256(canonical(record)).digest()
 required=b'\x00\x01'+b'\xff'*(width-len(digest)-3)+b'\x00'+digest
 encoded=pow(int.from_bytes(sig,'big'),e,n).to_bytes(width,'big')
 import hmac
 if not hmac.compare_digest(encoded,required):raise Refused('Signature differs')
 return record['result']
