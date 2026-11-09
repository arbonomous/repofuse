import pathlib,sys,json
sys.path.insert(0,str(pathlib.Path(__file__).parent.parent))
from repofuse.api_evidence import package_api

def test_package_paths_not_misc_flat_names(tmp_path):
 (tmp_path/'src/libx').mkdir(parents=True);(tmp_path/'src/libx/__init__.py').write_text('class Cache:\n pass\n');(tmp_path/'src/libx/keys.py').write_text('def hashkey(*args,**kwargs):\n return args\n')
 (tmp_path/'misc').mkdir();(tmp_path/'misc/demo.py').write_text('class FakeAPI:\n pass\n')
 d=package_api(tmp_path,'libx');rows=d['exports'];assert any(x['module']=='libx.keys' and x['name']=='hashkey' for x in rows);assert not any(x['name']=='FakeAPI' for x in rows)

def test_no_source_execution(tmp_path):
 (tmp_path/'libx').mkdir();(tmp_path/'libx/__init__.py').write_text("raise RuntimeError('MUST NOT EXECUTE')\ndef valid(a,b=1):\n return a\n")
 d=package_api(tmp_path,'libx');assert d['exports'][0]['signature']=='a, b=1'

def test_single_file_module(tmp_path):
 (tmp_path/'mypy_extensions.py').write_text('def Arg(name, type=None):\n return name\nclass TypedDict:\n pass\n')
 d=package_api(tmp_path,'mypy_extensions')
 assert d['status']=='static_declarations_only'
 names={x['name'] for x in d['exports']}
 assert names=={'Arg','TypedDict'}
 assert all(x['module']=='mypy_extensions' for x in d['exports'])

def test_symlink_package_refused(tmp_path):
 (tmp_path/'else').mkdir();(tmp_path/'else/__init__.py').write_text('def bad():pass');(tmp_path/'libx').symlink_to(tmp_path/'else')
 assert package_api(tmp_path,'libx')['status']=='not_resolved'
