import importlib.util,pathlib,sys
import pytest
HERE=pathlib.Path(__file__).parent
sys.path[:0]=[str(HERE),str(HERE.parent)]
old=sys.argv;sys.argv=['serve.py'];spec=importlib.util.spec_from_file_location('integrated_preflight_serve',HERE/'serve.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s);sys.argv=old
RID='run-0123456789abcdef'
@pytest.fixture
def case(tmp_path,monkeypatch):
 root=tmp_path/'fusion';gen=root/'fused_app/generated';gen.mkdir(parents=True)
 run={'run_id':RID,'status':'awaiting_review','events':[]};events=[]
 monkeypatch.setattr(s,'_load_general_inputs',lambda rid:(str(root),{},[],''));monkeypatch.setattr(s,'_general_attestation_path',lambda rid:str(tmp_path/'ack.json'));monkeypatch.setattr(s,'emit',lambda *a:events.append(a))
 return root,gen,run,events

def test_broken_script_blocks_before_review_or_execution(case,monkeypatch):
 root,gen,run,events=case;(gen/'app.py').write_text("HTML_PAGE = '<script>const a=;</script>'")
 from repofuse import gluereview,verify
 monkeypatch.setattr(gluereview,'check_attestation',lambda *a:pytest.fail('must stop before gate/execution'));monkeypatch.setattr(verify,'verify_fused_app',lambda *a,**k:pytest.fail('no execution'))
 s._general_review_or_verify(run,RID)
 assert run['status']=='frontend_preflight_failed';assert run['frontend_preflight']['status']=='failed';assert run['frontend_preflight']['browser_acceptance']=='not_run'

def test_valid_syntax_does_not_grant_attestation(case,monkeypatch):
 root,gen,run,events=case;(gen/'app.py').write_text("HTML_PAGE = '<script>1;</script>'")
 from repofuse import gluereview,verify
 monkeypatch.setattr(gluereview,'check_attestation',lambda *a:(False,'review required',[]));monkeypatch.setattr(verify,'verify_fused_app',lambda *a,**k:pytest.fail('no execution without review'))
 s._general_review_or_verify(run,RID)
 assert run['status']=='awaiting_review';assert run['frontend_preflight']['status']=='syntax_checked';assert (root/'review-request.json').is_file()

def test_missing_parser_is_loud_not_browser_pass(case,monkeypatch):
 root,gen,run,events=case;(gen/'app.py').write_text("HTML_PAGE = '<script>1;</script>'")
 import browser_preflight
 monkeypatch.setattr(browser_preflight.shutil,'which',lambda _:None)
 assert s._frontend_preflight(run,str(root/'fused_app'))
 assert run['frontend_preflight']['status']=='not_checked';assert 'FRONTEND NOT CHECKED' in events[-1][3]

def test_reviewed_backend_pass_does_not_claim_browser(case,monkeypatch):
 root,gen,run,events=case;(gen/'app.py').write_text("HTML_PAGE = '<script>1;</script>'")
 from repofuse import gluereview,verify
 monkeypatch.setattr(gluereview,'check_attestation',lambda *a:(True,'matched',[]));monkeypatch.setattr(verify,'verify_fused_app',lambda *a,**k:{'status':'passed'})
 s._general_review_or_verify(run,RID)
 assert run['status']=='build_verified';assert run['frontend_preflight']['browser_acceptance']=='not_run';assert any('Browser acceptance is NOT established' in e[3] for e in events)

def test_dynamic_html_not_fully_checked(case):
 root,gen,run,events=case;(gen/'app.py').write_text("HTML_PAGE = make_html()")
 assert s._frontend_preflight(run,str(root/'fused_app'));assert run['frontend_preflight']['status']=='not_checked'

def test_mixed_dynamic_html_not_full_syntax_claim(case):
 root,gen,run,events=case;(gen/'app.py').write_text("HTML_PAGE = '<script>1;</script>'");(gen/'other.py').write_text('HTML_PAGE = dynamic()')
 assert s._frontend_preflight(run,str(root/'fused_app'));assert run['frontend_preflight']['status']=='not_checked'

def test_no_node_approvals_or_provider_changes_in_integration():
 source=(HERE/'serve.py').read_text();assert 'if not _frontend_preflight(run, fusion_dir):' in source
 assert 'frontend_preflight_failed' in source


def test_multiple_html_assignments_not_hidden_by_other_valid_file(case):
 root,gen,run,events=case;(gen/'app.py').write_text("HTML_PAGE = '<script>1;</script>'");(gen/'other.py').write_text("HTML_PAGE = 'x'\nHTML_PAGE = 'y'\n")
 assert s._frontend_preflight(run,str(root/'fused_app'));assert run['frontend_preflight']['status']=='not_checked'
