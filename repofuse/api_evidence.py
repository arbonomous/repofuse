"""Static Python package/module/export evidence. No imports or source execution.

Facts are bounded AST declarations, not a guarantee a package imports safely.
Only matching package roots under repo/, src/, lib/ are treated as candidates;
examples/tests/misc scripts remain nonimportable candidates, never APIs.
Declarations whose module imports something outside the standard library and
the package itself are omitted, because the contained app does not install
those dependencies. A repository with no Python package exposes two surface
functions instead.
"""
import ast,pathlib,re,sys
MAX_FILES=500;MAX_BYTES=512*1024;MAX_APIS=36
IDENT=re.compile(r'^[A-Za-z_]\w*$')
_STDLIB=sys.stdlib_module_names

def python_ident(slug):
 ident=re.sub(r'[^A-Za-z0-9]+','_',slug or '').strip('_')
 if not ident or ident[0].isdigit():ident='repo_'+ident
 return ident

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
 constants=0
 for node in tree.body:
  if constants>=8 or not isinstance(node,ast.Assign):continue
  for target in node.targets:
   if isinstance(target,ast.Name) and target.id.isupper() and not target.id.startswith('_'):
    rows.append({'module':module,'name':target.id,'kind':'constant','signature':'constant','file':path.relative_to(root).as_posix()})
    constants+=1
    if constants>=8:break

def _module_parts(package, path, slug):
 rel=path.relative_to(package);parts=list(rel.with_suffix('').parts)
 if parts[-1]=='__init__':parts.pop()
 if any(not IDENT.fullmatch(part) for part in parts):return None
 return tuple([slug]+parts)

def _needs(tree, module_parts, is_init):
 needed=set()
 for node in ast.walk(tree):
  if isinstance(node,ast.Import):
   for alias in node.names:
    root=alias.name.split('.')[0]
    if root in _STDLIB:continue
    if root!=module_parts[0]:return None
    needed.add(tuple(alias.name.split('.')))
  elif isinstance(node,ast.ImportFrom):
   if node.level:
    base=list(module_parts if is_init else module_parts[:-1])
    drop=node.level-1
    if drop:base=base[:max(0,len(base)-drop)]
    if node.module:
     needed.add(tuple(base+node.module.split('.')))
    else:
     for alias in node.names:needed.add(tuple(base+[alias.name]))
    continue
   root=(node.module or '').split('.')[0]
   if root in _STDLIB:continue
   if root!=module_parts[0]:return None
   needed.add(tuple((node.module or '').split('.')))
 return needed

def _pure(parsed):
 candidates={}
 for key,(tree,is_init) in parsed.items():
  needed=_needs(tree,key,is_init)
  if needed is not None:candidates[key]=needed
 changed=True
 while changed:
  changed=False
  for key,needed in list(candidates.items()):
   if any(dep not in candidates for dep in needed):
    del candidates[key];changed=True
 return set(candidates)

def _surface(slug):
 ident=python_ident(slug);module=f'vendor.surfaces.{ident}';file=f'surfaces/{ident}.py'
 return {'status':'static_declarations_only','exports':[
  {'module':module,'name':'exports','kind':'function','signature':'()','file':file},
  {'module':module,'name':'read_text','kind':'function','signature':'(rel, limit=4000)','file':file}],
  'exports_total':2,'truncated':False,
  'note':'No importable Python package. Call exports() and read_text(rel) on this surface. They read vendored files and do not execute the repository.'}

def package_api(repo_root,slug):
 root=pathlib.Path(repo_root);candidates=[root/slug,root/'src'/slug,root/'lib'/slug]
 package=next((p for p in candidates if not p.is_symlink() and (p/'__init__.py').is_file() and not (p/'__init__.py').is_symlink()),None)
 module_file=root/(slug+'.py')
 if package is None and (module_file.is_symlink() or not module_file.is_file()):
  if (root/slug).is_symlink():
   return {'status':'not_resolved','exports':[],'note':'No matching regular Python package root found; no importability inferred from flat names.'}
  return _surface(slug)
 rows=[];truncated=False
 if package is not None:
  files=sorted(package.rglob('*.py'));truncated=len(files)>MAX_FILES
  parsed={}
  for p in files[:MAX_FILES]:
   if any(x.is_symlink() for x in p.parents if x!=root.parent):continue
   if p.is_symlink() or p.stat().st_size>MAX_BYTES:continue
   parts=_module_parts(package,p,slug)
   if parts is None:continue
   try:tree=ast.parse(p.read_text(encoding='utf-8'))
   except (OSError,UnicodeError,SyntaxError):continue
   parsed[parts]=(tree,p.name=='__init__.py',p)
  pure=_pure({key:(tree,is_init) for key,(tree,is_init,_p) in parsed.items()})
  for parts,(_tree,_is_init,p) in parsed.items():
   if parts in pure:_declarations(p, root, '.'.join(parts), rows)
 else:
  try:tree=ast.parse(module_file.read_text(encoding='utf-8'))
  except (OSError,UnicodeError,SyntaxError):tree=None
  if tree is not None and _needs(tree,(slug,),False) is not None:
   _declarations(module_file, root, slug, rows)
 if not rows:return _surface(slug)
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
