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

def test_third_party_import_is_omitted(tmp_path):
 (tmp_path/'libx').mkdir()
 (tmp_path/'libx/__init__.py').write_text('VERSION = "1"\n')
 (tmp_path/'libx/errors.py').write_text('class DisabledError(Exception):\n pass\n')
 (tmp_path/'libx/net.py').write_text('import requests\ndef fetch():\n return 1\n')
 names={x['name'] for x in package_api(tmp_path,'libx')['exports']}
 assert 'DisabledError' in names and 'VERSION' in names and 'fetch' not in names

def test_javascript_repo_exposes_a_surface(tmp_path):
 (tmp_path/'bot.ts').write_text('export function watch(){ return 1 }\n')
 d=package_api(tmp_path,'solana-trading-bot')
 assert {x['name'] for x in d['exports']}=={'exports','read_text'}
 assert d['exports'][0]['module']=='vendor.surfaces.solana_trading_bot'

def test_surface_reads_only_inside_the_repo(tmp_path):
 import importlib.util
 from repofuse.vendor import write_surfaces
 fusion=tmp_path/'fused'
 repo=fusion/'vendor'/'solana-trading-bot'
 repo.mkdir(parents=True)
 (repo/'bot.ts').write_text('export const n = 1\n')
 write_surfaces(fusion,[{'slug':'solana-trading-bot'}],[{'slug':'solana-trading-bot','exports':['watch']}])
 path=fusion/'vendor'/'surfaces'/'solana_trading_bot.py'
 spec=importlib.util.spec_from_file_location('surface_under_test',path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 assert module.exports()==['watch']
 assert 'export const' in module.read_text('bot.ts')
 try:
  module.read_text('../secret')
  raise AssertionError('path escaped')
 except ValueError:
  pass
