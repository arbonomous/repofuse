"""Offline prompt-contract tests, not real model/browser proof."""
import pathlib,sys,json
sys.path.insert(0,str(pathlib.Path(__file__).parent.parent))
from repofuse.synthesize import build_glue_prompt,build_test_prompt
def test_cache_closure_and_nonfinite_prompt():
 d=json.loads(build_glue_prompt({}, {})[1]['content'])
 assert 'closure still retains the old cache' in d['task']
 assert 'explicit lookup and insertion' in d['task']
 assert 'reset its hit/miss counters' in d['task']
 assert 'Reject nonfinite' in d['task']
 assert 'positional parameter that has no default' in d['task']
def test_exact_test_module_evidence():
 facts={'pkg':{'exports':[{'module':'pkg.keys','name':'hashkey'}]}}
 d=json.loads(build_test_prompt({'acceptance_criteria':[]},{},{'integration.py':'# retained'},api_evidence=facts)[1]['content'])
 assert d['python_api_evidence']==facts
 assert 'never assume from package import name' in d['module_rules']
 assert 'TWO non-default' in d['behavior_checks']
 assert 'first miss then second hit' in d['behavior_checks']
 assert d['glue_source']=={'integration.py':'# retained'}
