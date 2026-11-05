"""Offline-only exact disclosure import. No source execution or provider calls.

Use only the JSON returned by the actual independent reviewer through the
trusted conversation. Attribution in JSON is NOT authentication by itself.
"""
import json,pathlib,stat,argparse
from disclosure import check_review
from model_ideas import prepare
from review_exchange import RUN_ID,Refused,_atomic_json

def import_disclosure(record_path,studio_root):
 root=pathlib.Path(studio_root)
 p=pathlib.Path(record_path)
 if root.is_symlink() or not p.is_file() or p.is_symlink() or p.stat().st_size>128000:raise Refused('Invalid offline review record/root')
 record=json.loads(p.read_text());rid=record.get('run_id','')
 if not RUN_ID.fullmatch(rid):raise Refused('Invalid exact run id')
 planning=root/'runs'/(rid+'-planning');metas=planning/'metas.json';acks=root/'disclosure-acks'
 if any(q.is_symlink() for q in (root/'runs',planning,metas,acks)) or not metas.is_file():raise Refused('Invalid local planning state')
 prepared=prepare(json.loads(metas.read_text()),rid)
 check_review(record,prepared[-1])
 _atomic_json(acks/(rid+'.json'),record)
 return {'run_id':rid,'disclosure_imported':True,'execution_approved':False}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('record');parser.add_argument('--studio-root',default=str(pathlib.Path(__file__).resolve().parent));args=parser.parse_args()
 try:print(json.dumps(import_disclosure(args.record,args.studio_root)))
 except (ValueError,OSError,TypeError,KeyError):parser.exit(1,'Disclosure import refused; no provider call or execution approval.\n')
if __name__=='__main__':main()
