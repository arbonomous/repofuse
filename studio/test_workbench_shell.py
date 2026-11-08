"""Fixed shell tests with explicit inert integration, not genuine model evidence."""
import importlib.util,pathlib,types,sys,io,json
import pytest

def load(monkeypatch):
 pkg=types.ModuleType('generated');pkg.integration=types.SimpleNamespace(describe=lambda:dict(title='Fixed fixture',description='Explicit offline integration fixture',example={'numbers':[1,2]}),compute=lambda p:p)
 monkeypatch.setitem(sys.modules,'generated',pkg)
 path=pathlib.Path(__file__).parent.parent/'repofuse/workbench_shell.py';spec=importlib.util.spec_from_file_location('fixed_shell_test',path);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s);return s

def call(s,path='/',method='GET',raw=b'',length=None):
 capture={};env={'PATH_INFO':path,'REQUEST_METHOD':method,'CONTENT_LENGTH':str(len(raw)) if length is None else length,'wsgi.input':io.BytesIO(raw)}
 def sr(status,headers):capture['status']=status;capture['headers']=dict(headers)
 body=b''.join(s.app(env,sr));return capture,body

def test_object_fields_remain_json(monkeypatch):
    page = load(monkeypatch).HTML_PAGE
    assert "function structured(v)" in page
    assert "JSON.stringify(v,null,2)" in page
    assert page.index("function structured") < page.index(".join(', ')")

def test_shell_real_json_roundtrip(monkeypatch):
 s=load(monkeypatch);c,b=call(s,'/api/run','POST',b'{"x":1}');assert c['status']=='200 OK';assert json.loads(b)=={'result':{'x':1}}
 c,b=call(s,'/api/describe');assert json.loads(b)['title']=='Fixed fixture'
 c,b=call(s);assert b'Fixed RepoFuse HTTP/UI shell' in b
@pytest.mark.parametrize('length,code',[('',400),('-1',400),('abc',400),('65537',413),('99999999999999999',413),('１２',400)])
def test_lengthguards(monkeypatch,length,code):
 c,b=call(load(monkeypatch),'/api/run','POST',length=length);assert c['status'].startswith(str(code))
def test_invalid_json_and_methods(monkeypatch):
 s=load(monkeypatch)
 for raw in (b'[]',b'{',b'{"x":NaN}'):
  assert call(s,'/api/run','POST',raw)[0]['status']=='400 Bad Request'
 assert call(s,'/api/run')[0]['status']=='405 Method Not Allowed'
 assert call(s,'/missing')[0]['status']=='404 Not Found'
def test_integration_exceptions_hidden(monkeypatch):
 s=load(monkeypatch)
 def fail(p):raise RuntimeError('private diagnostic must not leak')
 s.integration.compute=fail;c,b=call(s,'/api/run','POST',b'{}');assert c['status']=='500 Internal Server Error';assert b'private diagnostic' not in b
