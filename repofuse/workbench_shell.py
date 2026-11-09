"""Assistant-authored fixed HTTP/UI shell. Model integration is separate untrusted code.
No shell import into generator process. This file is copied as attested generated/app.py.
"""
import json,math
from generated import integration
HTML_PAGE='''<!doctype html><html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>RepoFuse</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;font:16px/1.45 system-ui,sans-serif;background:#0b1220;color:#e8eefc}
.app{display:grid;grid-template-columns:220px 1fr;min-height:100vh}nav{background:#121a2b;padding:20px 14px;border-right:1px solid #243049}
nav .brand{margin:0 8px 18px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#8ea0c2}
nav button{display:block;width:100%;text-align:left;background:transparent;color:inherit;border:0;border-radius:8px;padding:10px 12px;margin:4px 0}
nav button.on{background:#243454}main{padding:28px 32px 48px;max-width:980px}header h1{margin:0 0 8px;font-size:32px}
header p{margin:0 0 8px;color:#c5d2ea}.actions{display:flex;gap:12px;align-items:center;margin:18px 0 8px}
button.run,button.add{background:#3b82f6;color:#fff;border:0;border-radius:8px;padding:10px 16px}
button.remove{background:transparent;color:#ffb4b4;border:1px solid #5a3340;border-radius:8px;padding:6px 10px}
table{width:100%;border-collapse:collapse;background:#121a2b;border-radius:12px;overflow:hidden}
th,td{padding:10px 12px;border-bottom:1px solid #243049;text-align:left;vertical-align:top}
input,textarea{width:100%;background:#0b1220;color:inherit;border:1px solid #31425f;border-radius:8px;padding:10px 12px;margin:8px 0 16px}
textarea{min-height:8em}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:8px 0 18px}
.metric{background:#121a2b;border:1px solid #243049;border-radius:12px;padding:14px}.metric span{display:block;color:#8ea0c2;font-size:13px}
.metric strong{font-size:28px}pre{white-space:pre-wrap;background:#121a2b;padding:16px;border-radius:12px;overflow:auto}
#error{color:#ffb4b4}.view{display:none}.view.on{display:block}footer,summary{color:#8ea0c2;font-size:13px}
details{margin-top:28px}#status{color:#c5d2ea}
@media(max-width:800px){.app{grid-template-columns:1fr}nav{display:flex;gap:8px;overflow:auto;border-right:0;border-bottom:1px solid #243049}nav button{width:auto;white-space:nowrap}}
</style><div class=app><nav id=nav></nav><main><header><h1 id=title>RepoFuse</h1><p id=description>Loading the application.</p><div class=actions><button class=run id=run>Run</button><span id=status>Ready</span></div><p id=error></p></header><div id=views></div><details><summary>Request and response</summary><label for=input>JSON input</label><textarea id=input>{}</textarea><pre id=output>Results appear here.</pre></details><footer>Fixed RepoFuse HTTP/UI shell. The calculation is generated integration logic.</footer></main></div><script>
const el=id=>document.getElementById(id);let example={};
function structured(v){return Array.isArray(v)?v.some(x=>x&&typeof x==='object'):!!v&&typeof v==='object'}
function isRecords(v){return Array.isArray(v)&&v.length>0&&v.every(x=>x&&typeof x==='object'&&!Array.isArray(x))}
function showValue(v){if(structured(v))return JSON.stringify(v,null,2);if(Array.isArray(v))return v.join(', ');return String(v)}
function readValue(raw,old){if(structured(old))return JSON.parse(raw);if(Array.isArray(old)){return raw.split(',').map(x=>{const t=x.trim();return typeof old[0]==='number'?Number(t):t}).filter(x=>x!==''&&!(typeof x==='number'&&Number.isNaN(x)))}if(typeof old==='number')return Number(raw);if(typeof old==='boolean')return raw==='true';return raw}
function label(k){return String(k).replace(/_/g,' ')}
function onEdit(){try{sync();el('error').textContent=''}catch(e){el('error').textContent='Check input values'}}
function fieldValue(node,old){if(node.dataset.kind==='records'){const rows=[];node.querySelectorAll('tbody tr').forEach(tr=>{const row={};tr.querySelectorAll('[data-col]').forEach(input=>{const sample=old[0]?old[0][input.dataset.col]:'';row[input.dataset.col]=readValue(input.value,sample)});rows.push(row)});return rows}return readValue(node.value,old)}
function sync(){const p={};el('views').querySelectorAll('[data-key]').forEach(node=>{p[node.dataset.key]=fieldValue(node,example[node.dataset.key])});el('input').value=JSON.stringify(p,null,2)}
function records(key,rows){const wrap=document.createElement('div');wrap.dataset.key=key;wrap.dataset.kind='records';const cols=Object.keys(rows[0]||{});const table=document.createElement('table');const head=document.createElement('tr');cols.forEach(c=>{const th=document.createElement('th');th.textContent=label(c);head.append(th)});const end=document.createElement('th');head.append(end);const thead=document.createElement('thead');thead.append(head);const body=document.createElement('tbody');function add(row){const tr=document.createElement('tr');cols.forEach(c=>{const td=document.createElement('td');const input=document.createElement('input');input.dataset.col=c;input.value=row[c]==null?'':String(row[c]);input.oninput=onEdit;td.append(input);tr.append(td)});const td=document.createElement('td');const rm=document.createElement('button');rm.type='button';rm.className='remove';rm.textContent='Remove';rm.onclick=()=>{tr.remove();sync()};td.append(rm);tr.append(td);body.append(tr)}rows.forEach(add);table.append(thead,body);const addBtn=document.createElement('button');addBtn.type='button';addBtn.className='add';addBtn.textContent='Add row';addBtn.onclick=()=>{const blank={};cols.forEach(c=>{blank[c]=typeof rows[0][c]==='number'?0:''});add(blank);sync()};wrap.append(table,addBtn);return wrap}
function dataTable(rows){const table=document.createElement('table');const cols=Object.keys(rows[0]||{});const head=document.createElement('tr');cols.forEach(c=>{const th=document.createElement('th');th.textContent=label(c);head.append(th)});const thead=document.createElement('thead');thead.append(head);const body=document.createElement('tbody');rows.forEach(row=>{const tr=document.createElement('tr');cols.forEach(c=>{const td=document.createElement('td');const cell=row[c];td.textContent=cell&&typeof cell==='object'?JSON.stringify(cell):String(cell??'');tr.append(td)});body.append(tr)});table.append(thead,body);return table}
function show(value,parent){if(value&&typeof value==='object'){const table=document.createElement('table');Object.entries(value).forEach(([k,v])=>{const row=table.insertRow(),key=row.insertCell(),cell=row.insertCell();key.textContent=label(k);if(v&&typeof v==='object')show(v,cell);else cell.textContent=String(v)});parent.append(table)}else{const p=document.createElement('p');p.textContent=String(value);parent.append(p)}}
function showView(id){document.querySelectorAll('.view').forEach(v=>v.classList.toggle('on',v.id===id));document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('on',b.dataset.view===id))}
function inputs(){const nav=el('nav'),views=el('views');nav.replaceChildren();views.replaceChildren();const brand=document.createElement('p');brand.className='brand';brand.textContent='RepoFuse';nav.append(brand);const scalars=[];let first='';function addNav(id,text){const b=document.createElement('button');b.type='button';b.dataset.view=id;b.textContent=text;b.onclick=()=>showView(id);nav.append(b);if(!first)first=id}Object.entries(example).forEach(([k,v])=>{if(!isRecords(v)){scalars.push([k,v]);return}const id='view-'+k;addNav(id,label(k));const section=document.createElement('section');section.id=id;section.className='view';const h=document.createElement('h2');h.textContent=label(k);section.append(h,records(k,v));views.append(section)});if(scalars.length){addNav('view-settings','Settings');const section=document.createElement('section');section.id='view-settings';section.className='view';const h=document.createElement('h2');h.textContent='Settings';section.append(h);scalars.forEach(([k,v])=>{const lab=document.createElement('label');lab.textContent=label(k);const input=document.createElement(structured(v)?'textarea':'input');input.dataset.key=k;input.value=showValue(v);input.oninput=onEdit;lab.append(input);section.append(lab)});views.append(section)}addNav('view-results','Results');const board=document.createElement('section');board.id='view-results';board.className='view';const h=document.createElement('h2');h.textContent='Results';const empty=document.createElement('p');empty.id='empty';empty.textContent='Run the app to fill this board.';const metrics=document.createElement('div');metrics.id='metrics';metrics.className='metrics';const out=document.createElement('div');out.id='results';board.append(h,empty,metrics,out);views.append(board);showView(first||'view-results')}
function renderResult(value){el('empty').hidden=true;el('metrics').replaceChildren();el('results').replaceChildren();if(!value||typeof value!=='object'||Array.isArray(value)){show(value,el('results'));return}Object.entries(value).forEach(([k,v])=>{if(typeof v==='number'&&Number.isFinite(v)){const card=document.createElement('div');card.className='metric';const name=document.createElement('span');name.textContent=label(k);const num=document.createElement('strong');num.textContent=String(v);card.append(name,num);el('metrics').append(card);return}const block=document.createElement('section');const h=document.createElement('h3');h.textContent=label(k);block.append(h);if(isRecords(v))block.append(dataTable(v));else if(typeof v==='string'&&v.length>160){const pre=document.createElement('pre');pre.textContent=v;block.append(pre)}else if(v&&typeof v==='object')show(v,block);else{const p=document.createElement('p');p.textContent=String(v);block.append(p)}el('results').append(block)})}
async function init(){try{const r=await fetch('/api/describe');const d=await r.json();if(!r.ok)throw Error(d.error);el('title').textContent=d.title;document.title=d.title;el('description').textContent=d.description;example=d.example;el('input').value=JSON.stringify(example,null,2);inputs()}catch(e){el('error').textContent=e.message}}
el('run').onclick=async()=>{el('error').textContent='';el('status').textContent='Running';el('run').disabled=true;try{sync();const payload=JSON.parse(el('input').value);const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');el('output').textContent=JSON.stringify(d,null,2);renderResult(d.result);showView('view-results');el('status').textContent='Done'}catch(e){el('error').textContent=e.message;el('status').textContent='Failed'}finally{el('run').disabled=false}};init();
</script></html>'''
REASONS={200:'OK',400:'Bad Request',404:'Not Found',405:'Method Not Allowed',413:'Payload Too Large',500:'Internal Server Error'}
def reply(sr,code,value,html=False):
 try:body=value.encode() if html else json.dumps(value,allow_nan=False).encode()
 except (TypeError,ValueError):code=500;body=b'{"error":"Integration returned unsupported JSON"}'
 if len(body)>262144:code=500;body=b'{"error":"Integration response exceeds limit"}'
 sr(str(code)+' '+REASONS[code],[('Content-Type','text/html; charset=utf-8' if html else 'application/json'),('Content-Length',str(len(body))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]);return [body]
def app(env,sr):
 path=env.get('PATH_INFO','/');method=env.get('REQUEST_METHOD','GET')
 if path=='/' and method=='GET':return reply(sr,200,HTML_PAGE,True)
 if path=='/api/describe':
  if method!='GET':return reply(sr,405,{'error':'GET required'})
  try:
   d=integration.describe()
   if not isinstance(d,dict) or set(d)!={'title','description','example'} or not all(isinstance(d[k],str) and 1<=len(d[k])<=600 for k in ('title','description')) or not isinstance(d['example'],dict):raise ValueError()
   return reply(sr,200,d)
  except Exception:return reply(sr,500,{'error':'Invalid integration description'})
 if path!='/api/run':return reply(sr,404,{'error':'Route not found'})
 if method!='POST':return reply(sr,405,{'error':'POST required'})
 raw_length=env.get('CONTENT_LENGTH','')
 if not isinstance(raw_length,str) or not raw_length.isascii() or not raw_length.isdecimal():return reply(sr,400,{'error':'Decimal CONTENT_LENGTH required'})
 if len(raw_length)>6:return reply(sr,413,{'error':'Input exceeds limit'})
 length=int(raw_length)
 if length>65536:return reply(sr,413,{'error':'Input exceeds limit'})
 try:
  raw=env['wsgi.input'].read(length)
  if len(raw)!=length:raise ValueError()
  payload=json.loads(raw.decode('utf-8'),parse_constant=lambda x:(_ for _ in ()).throw(ValueError()))
  if not isinstance(payload,dict):raise ValueError()
 except (ValueError,UnicodeError,KeyError):return reply(sr,400,{'error':'JSON object required'})
 try:return reply(sr,200,{'result':integration.compute(payload)})
 except (ValueError,TypeError,KeyError):return reply(sr,400,{'error':'Integration rejected input'})
 except Exception:return reply(sr,500,{'error':'Integration failed'})
