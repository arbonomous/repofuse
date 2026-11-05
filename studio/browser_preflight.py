"""Static embedded-JavaScript syntax check, never a safety approval.

Parses Python AST without importing the generated file. Checks only literal
HTML_PAGE assignments and inline JavaScript using node --check (no code run).
Not a replacement for exact-source review or real browser acceptance.
"""
import ast
from html.parser import HTMLParser
import pathlib
import shutil
import subprocess

MAX_SOURCE_BYTES=512*1024
MAX_SCRIPT_CHARS=128*1024
class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False);self.scripts=[];self.current=None;self.external=0;self.skipped=0
    def handle_starttag(self, tag, attrs):
        if tag.lower()!='script':return
        attrs=dict(attrs)
        if 'src' in attrs:self.external+=1;self.current=None;return
        mime=attrs.get('type','').lower().strip()
        if mime not in ('','text/javascript','application/javascript','module'):
            self.skipped+=1;self.current=None;return
        self.current={'mode':'module' if mime=='module' else 'script','text':''}
    def handle_data(self,data):
        if self.current is not None:self.current['text']+=data
    def handle_endtag(self,tag):
        if tag.lower()=='script' and self.current is not None:self.scripts.append(self.current);self.current=None

def check_source(path,node_path=None):
    p=pathlib.Path(path)
    if p.is_symlink() or not p.is_file():return {'status':'blocked','reason':'regular source file required'}
    if p.stat().st_size>MAX_SOURCE_BYTES:return {'status':'blocked','reason':'source exceeds bound'}
    try:
        source=p.read_text(encoding='utf-8');compile(source,str(p),'exec',dont_inherit=True);tree=ast.parse(source)
    except (SyntaxError,UnicodeError) as e:return {'status':'failed','reason':'Python source parse failed: '+str(e)}
    values=[]
    for stmt in tree.body:
        targets=stmt.targets if isinstance(stmt,ast.Assign) else [stmt.target] if isinstance(stmt,ast.AnnAssign) else []
        if any(isinstance(t,ast.Name) and t.id=='HTML_PAGE' for t in targets):
            if not isinstance(stmt.value,ast.Constant) or not isinstance(stmt.value.value,str):return {'status':'not_checked','reason':'HTML_PAGE is not a static string literal'}
            values.append(stmt.value.value)
    if not values:return {'status':'not_checked','reason':'no HTML_PAGE assignment'}
    if len(values)!=1:return {'status':'not_checked','reason':'multiple HTML_PAGE assignments'}
    parser=Scripts();parser.feed(values[0]);parser.close()
    if parser.current is not None:return {'status':'failed','reason':'unclosed script element'}
    if not parser.scripts:return {'status':'not_checked','reason':'no supported inline scripts','external_scripts':parser.external}
    node=node_path or shutil.which('node')
    if not node:return {'status':'not_checked','reason':'JavaScript parser unavailable'}
    errors=[]
    for i,s in enumerate(parser.scripts):
        if len(s['text'])>MAX_SCRIPT_CHARS:return {'status':'blocked','reason':'inline script exceeds bound'}
        try:
            args=[node,'--check','--input-type=module'] if s['mode']=='module' else [node,'-e',"new (require('vm').Script)(require('fs').readFileSync(0,'utf8'))"]
            r=subprocess.run(args,input=s['text'],text=True,capture_output=True,timeout=5,env={'PATH':'/usr/bin:/bin'},cwd='/tmp')
        except (OSError,subprocess.TimeoutExpired):return {'status':'not_checked','reason':'JavaScript parser unavailable or timed out'}
        if r.returncode:errors.append({'script':i,'detail':r.stderr[:1500]})
    if errors:return {'status':'failed','reason':'inline JavaScript syntax error','errors':errors}
    # External code is never fetched, and syntax alone establishes no behavior.
    return {'status':'syntax_checked','inline_scripts':len(parser.scripts),'external_scripts_unchecked':parser.external,'non_javascript_scripts_skipped':parser.skipped,'execution_approved':False,'browser_acceptance_proven':False}
