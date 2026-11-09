"""Static Python package/module/export evidence. No imports or source execution.

Facts are bounded AST declarations, not a guarantee a package imports safely.
Only matching package roots under repo/, src/, lib/ are treated as candidates;
examples/tests/misc scripts remain nonimportable candidates, never APIs.
"""
import ast,pathlib,re
MAX_FILES=500;MAX_BYTES=512*1024;MAX_APIS=36
IDENT=re.compile(r'^[A-Za-z_]\w*$')

def _declarations(path, root, module, rows):
 if path.is_symlink() or path.stat().st_size>MAX_BYTES:return
 try:tree=ast.parse(path.read_text(encoding='utf-8'))
 except (OSError,UnicodeError,SyntaxError):return
 for node in tree.body:
   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and not node.name.startswith('_'):
    if isinstance(node,ast.ClassDef):
     init=next((n for n in node.body if isinstance(n,ast.FunctionDef) and n.name=='__init__'),None);args=ast.unparse(init.args)[:180] if init else 'signature not statically defined'
     kind='class'
    else:args=ast.unparse(node.args)[:180];kind='function'
    rows.append({'module':module,'name':node.name,'kind':kind,'signature':args,'file':path.relative_to(root).as_posix()})
def package_api(repo_root,slug):
 root=pathlib.Path(repo_root);candidates=[root/slug,root/'src'/slug,root/'lib'/slug]
 package=next((p for p in candidates if not p.is_symlink() and (p/'__init__.py').is_file() and not (p/'__init__.py').is_symlink()),None)
 module_file=root/(slug+'.py')
 if package is None and (module_file.is_symlink() or not module_file.is_file()):
  return {'status':'not_resolved','exports':[],'note':'No matching regular Python package root found; no importability inferred from flat names.'}
 rows=[];truncated=False
 if package is not None:
  files=sorted(package.rglob('*.py'));truncated=len(files)>MAX_FILES
  for p in files[:MAX_FILES]:
   if any(x.is_symlink() for x in p.parents if x!=root.parent):continue
   rel=p.relative_to(package);parts=list(rel.with_suffix('').parts)
   if parts[-1]=='__init__':parts.pop()
   if any(not IDENT.fullmatch(part) for part in parts):continue
   _declarations(p, root, '.'.join([slug]+parts), rows)
 else:
  _declarations(module_file, root, slug, rows)
 # Fair deterministic sample across modules, rather than alphabetic misc names.
 groups={}
 for row in rows:groups.setdefault(row['module'],[]).append(row)
 selected=[]
 while groups and len(selected)<MAX_APIS:
  for module in list(groups):
   selected.append(groups[module].pop(0))
   if not groups[module]:del groups[module]
   if len(selected)>=MAX_APIS:break
 return {'status':'static_declarations_only','exports':selected,'exports_total':len(rows),'truncated':truncated or len(rows)>len(selected),'note':'AST declaration module paths/signatures only; decorators, re-exports, aliases and runtime import success not verified. Use from module import name exactly; flat names do not imply top-level exports. Never import or execute source to infer these facts.'}
