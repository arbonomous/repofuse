"""Offline prompt/bound regression, not real generation success."""
import json,pathlib,sys
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).parent.parent))
from repofuse.synthesize import build_glue_prompt,validate_glue_size,GLUE_OUTPUT_CHAR_BUDGET
from repofuse.budget import BudgetExceeded

def test_prompt_retains_integration_fixed_shell_boundary():
 msgs=build_glue_prompt({'conflicts':[]},{'bridge':[]},intent='both chosen repos in actual browser app')
 d=json.loads(msgs[1]['content']);assert d['user_intent']=='both chosen repos in actual browser app'
 assert 'ONLY integration.py' in d['task'];assert 'BOTH-REPOSITORY' in d['task'];assert 'assistant-authored' in d['task'];assert '7500' in d['output_budget']

def test_no_partial_oversized_output():
 with pytest.raises(BudgetExceeded):validate_glue_size({'app.py':'x'*GLUE_OUTPUT_CHAR_BUDGET})

def test_empty_or_nonstring_not_accepted():
 for value in ({},[],{'app.py':123}):
  with pytest.raises(BudgetExceeded):validate_glue_size(value)

def test_small_complete_map_accepted():assert validate_glue_size({'app.py':"def app(e,s):\n s('200 OK',[]);return [b'ok']\n"})

def test_python_compile_before_write_guard():
 from repofuse.synthesize import validate_python_outputs
 for source in ("x = 1 !== 2", "CACHE=1\ndef f():\n print(CACHE)\n global CACHE\n"):
  with pytest.raises(BudgetExceeded):validate_python_outputs({'app.py':source})
 assert validate_python_outputs({'app.py':'VALUE=1\n'})
