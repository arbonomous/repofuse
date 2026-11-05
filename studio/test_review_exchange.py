import importlib.util,json,pathlib,sys,zipfile,io,hashlib
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
spec=importlib.util.spec_from_file_location('candidate_review_exchange',pathlib.Path(__file__).with_name('review_exchange.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
RID='run-0123456789abcdef'
def fixture(tmp_path):
 root=tmp_path/'studio';fr=root/'runs'/(RID+'-fusion');app=fr/'fused_app';(app/'generated').mkdir(parents=True);(app/'vendor').mkdir();(app/'generated/app.py').write_text('VALUE=1\n');(app/'vendor/lib.py').write_text('VALUE=2\n')
 run={'run_id':RID,'status':'ideas_ready','events':[{'data':{'slug':'alpha','commit':'a'*40}}],'safety':{'status':'warn','repos':[{'repo':'alpha','commit':'a'*40}]},'repo_a':'https://github.com/x/alpha'}
 (root/'runs'/(RID+'-state.json')).write_text(json.dumps(run));(fr/'metas.json').write_text('[]');(fr/'budget.json').write_text('DO-NOT-EXPORT');(fr/'raw_responses').mkdir();(fr/'raw_responses/key.txt').write_text('DO-NOT-EXPORT');return root,fr,app,run

def test_allowlist_export_no_runtime_secret_files(tmp_path):
 root,fr,app,run=fixture(tmp_path);data,name=m.export_bundle(run,root/'runs');z=zipfile.ZipFile(io.BytesIO(data));assert name==RID+'-review.zip';assert set(z.namelist())=={'README.txt','review.json','metas.json','fused_app/generated/app.py','fused_app/vendor/lib.py'};assert b'DO-NOT-EXPORT' not in data

def test_symlink_refused(tmp_path):
 root,fr,app,run=fixture(tmp_path);(app/'generated/link').symlink_to('/etc/passwd')
 with pytest.raises(m.Refused):m.export_bundle(run,root/'runs')

def test_exact_import_and_tamper_refusal(tmp_path):
 from repofuse import gluereview
 root,fr,app,run=fixture(tmp_path);rec=dict(m._binding(run),reviewer='independent fixture reviewer',whole_tree={'files':{p:gluereview._sha256(str(app/p)) for p in gluereview.review_targets(str(app))}});path=tmp_path/'record.json';path.write_text(json.dumps(rec));out=m.import_review(path,root);assert out['whole_tree_imported'];assert (root/'safety-acks'/(RID+'.json')).is_file();assert (root/'build-approvals'/(RID+'-general.json')).is_file()
 (app/'generated/app.py').write_text('CHANGED=1\n')
 with pytest.raises(m.Refused):m.import_review(path,root)

def test_wrong_binding_no_write(tmp_path):
 root,fr,app,run=fixture(tmp_path);rec=dict(m._binding(run),reviewer='fixture');rec['verdict_hash']='x';path=tmp_path/'record.json';path.write_text(json.dumps(rec))
 with pytest.raises(m.Refused):m.import_review(path,root)
 assert not (root/'safety-acks').exists()

def test_fail_unknown_refused(tmp_path):
 root,fr,app,run=fixture(tmp_path)
 for status in ['fail','unknown']:
  run['safety']['status']=status
  with pytest.raises(m.Refused):m.export_bundle(run,root/'runs')

def test_size_bound_no_partial(tmp_path,monkeypatch):
 root,fr,app,run=fixture(tmp_path);monkeypatch.setattr(m,'MAX_BYTES',1)
 with pytest.raises(m.Refused):m.export_bundle(run,root/'runs')
