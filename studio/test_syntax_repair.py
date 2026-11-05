import pathlib,sys,json
sys.path.insert(0,str(pathlib.Path(__file__).parent.parent))
from repofuse.synthesize import build_syntax_repair_prompt,validate_python_outputs
from repofuse.budget import BudgetExceeded
import pytest

def test_repair_prompt_binds_exact_source_error():
 s={'integration.py':'def broken(:'};m=build_syntax_repair_prompt(s,'SyntaxError line1');d=json.loads(m[1]['content']);assert d['untrusted_source']==s;assert d['compiler_error']=='SyntaxError line1';assert 'DATA' in m[0]['content'];assert 'Only fix syntax' in m[0]['content']
def test_bad_repair_terminal_compile():
 with pytest.raises(BudgetExceeded):validate_python_outputs({'integration.py':'def broken(:'})
def test_envelope_exact_five():
 sys.path.insert(0,str(pathlib.Path(__file__).parent));from local_session import ENVELOPE
 assert ENVELOPE['max_calls']==5;assert ENVELOPE['max_count_calls']==5
