import pathlib
from browser_preflight import check_source

def source(tmp_path,html):
 p=tmp_path/'app.py';p.write_text('HTML_PAGE = '+repr(html)+'\n');return p

def test_valid_script(tmp_path):
 r=check_source(source(tmp_path,'<script>const a=1;</script>'));assert r['status']=='syntax_checked';assert not r['execution_approved'];assert not r['browser_acceptance_proven']
def test_invalid_script(tmp_path):
 assert check_source(source(tmp_path,'<script>const a=;</script>'))['status']=='failed'
def test_does_not_execute_python_or_js(tmp_path):
 marker=tmp_path/'DO_NOT_CREATE';p=source(tmp_path,'<script>throw new Error("not executed");</script>');p.write_text(p.read_text()+f'open({str(marker)!r}, "w").write("bad")\n');assert check_source(p)['status']=='syntax_checked';assert not marker.exists()
def test_dynamic_html_not_checked(tmp_path):
 p=tmp_path/'a.py';p.write_text('HTML_PAGE = make_html()');assert check_source(p)['status']=='not_checked'
def test_external_script_not_fetched(tmp_path):
 r=check_source(source(tmp_path,'<script src="https://invalid.test/x.js"></script><script>1;</script>'));assert r['external_scripts_unchecked']==1
def test_invalid_python(tmp_path):
 p=tmp_path/'a.py';p.write_text('HTML_PAGE = (');assert check_source(p)['status']=='failed'
def test_unclosed_script(tmp_path):
 assert check_source(source(tmp_path,'<script>1;'))['status']=='failed'
def test_json_script_skipped(tmp_path):
 r=check_source(source(tmp_path,'<script type="application/ld+json">{"a":1}</script><script>1;</script>'));assert r['non_javascript_scripts_skipped']==1
def test_symlink_refused(tmp_path):
 p=source(tmp_path,'<script>1;</script>');l=tmp_path/'link.py';l.symlink_to(p);assert check_source(l)['status']=='blocked'
def test_parser_missing_not_pass(tmp_path):
 assert check_source(source(tmp_path,'<script>1;</script>'),'/not/a/parser')['status']=='not_checked'


def test_compile_semantics_reject_global_after_use(tmp_path):
    p=tmp_path/'bad.py';p.write_text("CACHE=1\ndef app(e,s):\n print(CACHE)\n global CACHE\n CACHE=2\n")
    assert check_source(p)['status']=='failed'
