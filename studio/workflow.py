"""Read-only readiness for a retained Studio run. Never grants approval."""
import json
import pathlib

def read_workflow(server, run):
    rid=run['run_id']; root=pathlib.Path(server.RUNS); status=run.get('status','unknown')
    result={'run_id':rid,'status':status,'generation_started':False,'actions':[],
            'relay':{'available':False,'detail':'A failed or unknown check stops this build. A warning and the unsent request hash for a clear pair are stored on this machine.'}}
    planning=root/(rid+'-planning')
    ledger=planning/'budget.json'
    if ledger.exists():
        try:
            data=json.loads(ledger.read_text())
            if not isinstance(data,dict) or not isinstance(data.get('calls',[]),list):raise ValueError('Malformed ledger')
            calls=data.get('calls',[])
            if any(not isinstance(c,dict) for c in calls):raise ValueError('Malformed call record')
            result['generation_started']=bool(calls)
            result['planning_attempt_recorded']=any(c.get('step')=='idea-suggest' for c in calls)
        except (OSError,ValueError,TypeError):
            result['blocked']='Attempt ledger is unreadable; no retry is offered.';return result
    try:
        _,_,prepared=server.Handler._planning_prepare(None,rid)
        from disclosure import check_review
        ack=json.loads((pathlib.Path(server.ROOT)/'disclosure-acks'/(rid+'.json')).read_text())
        check_review(ack,prepared[-1]);result['disclosure_review']='matched'
    except (OSError,ValueError,TypeError,KeyError):result['disclosure_review']='waiting'
    safe,why=server.spend_safety_gate(run);result['input_qualification']={'ready':safe,'detail':why}
    connected=server._local_session.status()['connected'];result['model_connected']=connected
    if status in ('awaiting_review','frontend_preflight_failed'):
        from repofuse import gluereview
        try:
            folder,_,_,_=server._load_general_inputs(rid)
            ok,reason,_=gluereview.check_attestation(str(pathlib.Path(folder)/'fused_app'),server._general_attestation_path(rid))
        except (OSError,ValueError,TypeError,KeyError):ok=False;reason='Retained build is unavailable or malformed.'
        result['source_review']={'matched':ok,'detail':reason}
        if safe and ok:result['actions']=['verify_reviewed_bytes']
    elif status=='build_verified':
        result['actions']=['check_and_serve_reviewed_app']
    elif status=='ideas_ready' and (planning/'model-ideas.json').is_file():
        result['actions']=['choose_retained_model_idea']
    elif result['disclosure_review']=='matched' and connected and not result.get('planning_attempt_recorded'):
        result['actions']=['request_model_ideas']
    result['frontend_preflight']=run.get('frontend_preflight',{'status':'not_run','browser_acceptance':'not_run'})
    result['note']='Readiness is informational. Every action rechecks its original gates; no provider call or source execution occurs here.'
    return result
