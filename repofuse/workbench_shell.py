"""Assistant-authored fixed HTTP/UI shell. Model integration is separate untrusted code.
No shell import into generator process. This file is copied as attested generated/app.py.

The page is the same for every pair of repositories. It turns describe() and
compute() into settings and an answer a person can read without source code.
"""
import json
from generated import integration
HTML_PAGE='''<!doctype html><html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Your page</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;font:17px/1.5 system-ui,sans-serif;background:#0e1524;color:#f2f6ff}
main{max-width:1180px;margin:0 auto;padding:28px 28px 64px}header h1{margin:0 0 8px;font-size:34px;letter-spacing:-.02em}
.brand{margin:0 0 8px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#8ea0c2}
header p{margin:0;color:#d5e0f5;max-width:46rem}.guide{margin:18px 0;background:#162033;border:1px solid #2a3a56;border-left:4px solid #7dd3a7;border-radius:14px;padding:14px 18px}
.guide h2,.callout h3,aside h2,#views h2{margin:0 0 8px}.guide h2,aside h2{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:#8ea0c2}
.guide ul{margin:0;padding-left:18px}.guide li{margin:4px 0}.actions{display:flex;gap:12px;align-items:center;margin:14px 0 0}
button.run,button.add,button.page{background:#3b6fd8;color:#fff;border:0;border-radius:8px;padding:10px 16px;font:inherit}
button.page{background:#1c2942;margin:0 8px 8px 0}button.page.on{outline:2px solid #7dd3a7}
button.remove{background:transparent;color:#ffb4b4;border:1px solid #5a3340;border-radius:8px;padding:6px 10px}
.pages:empty{display:none}.desk{display:grid;grid-template-columns:minmax(280px,360px) 1fr;gap:22px;align-items:start;margin-top:18px}
aside{background:#162033;border:1px solid #2a3a56;border-radius:14px;padding:16px 16px 8px}
.group{margin:0 0 16px;padding:0;border:0}.group legend{font-weight:600;margin-bottom:4px}
.record{border:1px solid #2a3a56;border-radius:12px;padding:10px 12px 4px;margin:0 0 10px;background:#0e1524}
table{width:100%;border-collapse:collapse;background:#121a2b;border-radius:12px;overflow:hidden;margin:8px 0 12px}
th,td{padding:10px 12px;border-bottom:1px solid #243049;text-align:left;vertical-align:top}
th{color:#b7c4de;font-weight:650;font-size:14px}
input,textarea{width:100%;background:#0b1220;color:inherit;border:1px solid #31425f;border-radius:8px;padding:10px 12px;margin:4px 0 8px;font:inherit}
input[type=checkbox]{width:1.15rem;height:1.15rem;margin:0 8px 0 0;accent-color:#7dd3a7}
label.switch,label.field{display:block;margin:0 0 12px;font-weight:650}label.switch{display:flex;align-items:center;font-weight:650}
.state{margin-left:8px;color:#b7c4de;font-weight:500}textarea{min-height:8em}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:8px 0 18px}
.metric{background:#162033;border:1px solid #2a3a56;border-radius:12px;padding:14px}.metric span{display:block;color:#b7c4de;font-size:14px}
.metric strong{font-size:32px}.metric strong.hero{font-size:44px}.metric small{display:block;margin-top:6px;color:#8ea0c2;font-size:13px}
.callout{background:#14281f;border:1px solid #245c45;border-radius:14px;padding:14px 16px;margin:0 0 16px}.callout h3{color:#b7f0d2}
.callout p{margin:6px 0 0}.hint{color:#b7c4de;font-size:14px;margin:0 0 8px;font-weight:450}
.checks{list-style:none;padding:0;margin:8px 0 16px}.checks li{display:flex;justify-content:space-between;gap:12px;padding:10px 12px;background:#162033;border-bottom:1px solid #243049}
.checks li:first-child{border-radius:12px 12px 0 0}.checks li:last-child{border-radius:0 0 12px 12px;border-bottom:0}
.yes,.no{display:inline-block;min-width:3rem;text-align:center;border-radius:999px;padding:2px 10px;font-size:14px;font-weight:650}
.yes{background:#163528;color:#b7f0d2}.no{background:#2a3142;color:#c5d0e4}
ul.names{margin:8px 0 16px;padding-left:18px}ul.names li{margin:4px 0;word-break:break-word}
pre{white-space:pre-wrap;background:#121a2b;padding:16px;border-radius:12px;overflow:auto;max-height:28em}
#error{color:#ffb4b4;min-height:1.2em}.view{display:none}.view.on{display:block}
footer,summary{color:#8ea0c2}footer{margin-top:28px;font-size:14px}details{margin-top:28px}
@media(max-width:800px){.desk{grid-template-columns:1fr}main{padding:18px 14px 48px}header h1{font-size:28px}}
</style><main><p class=brand>Your page</p><header><h1 id=title>Loading</h1><p id=description>Getting this page ready.</p><section class=guide><h2>How to use this</h2><ul id=guide><li>Change a setting. The answer updates by itself.</li></ul></section><div class=actions><button class=run id=run>Update answer</button><span id=status>Ready</span></div><p id=error></p></header><div class=pages id=pages></div><div class=desk><aside id=controls><h2>Your settings</h2></aside><div id=views></div></div><details><summary>Technical details</summary><p class=hint>This is the data the page sends and the data it gets back. You can use the page without reading it.</p><label for=input>Settings data</label><textarea id=input>{}</textarea><pre id=output>The answer will appear here.</pre></details><footer>This page runs on your computer from the two repositories chosen for this build.</footer></main><script>
const el=id=>document.getElementById(id);let example={};let timer=0;
const LEAD=['summary','note','meaning','explanation','message','headline','what_this_means'];
function structured(v){return Array.isArray(v)?v.some(x=>x&&typeof x==='object'):!!v&&typeof v==='object'}
function isRecords(v){return Array.isArray(v)&&v.length>0&&v.every(x=>x&&typeof x==='object'&&!Array.isArray(x))}
function isFlat(v){return !!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length>0&&Object.values(v).every(x=>x==null||typeof x==='string'||typeof x==='number'||typeof x==='boolean')}
function isChecks(v){return !!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length>0&&Object.values(v).every(x=>typeof x==='boolean')}
function isDocs(v){return !!v&&typeof v==='object'&&!Array.isArray(v)&&Object.values(v).some(x=>typeof x==='string'&&x.length>40)}
function isNames(v){return Array.isArray(v)&&v.length>0&&v.every(x=>typeof x==='string'||typeof x==='number')}
function isLead(k,v){return typeof v==='string'&&v.length>0&&v.length<=500&&LEAD.indexOf(k)>=0}
function label(k){
 const known={rows:'Results',items:'Results',results:'Results',checklist:'Checks',checks:'Checks',doc_snippets:'Documents',docs:'Documents',documents:'Documents',summary:'What this means',note:'What this means',meaning:'What this means',explanation:'What this means'};
 if(known[k])return known[k];
 let out='';const raw=String(k);
 for(let i=0;i<raw.length;i++){const ch=raw[i];if(ch==='_'||ch==='-'){out+=' ';continue}if(i>0&&ch>='A'&&ch<='Z'&&raw[i-1]>='a'&&raw[i-1]<='z')out+=' ';out+=ch}
 out=out.trim();if(!out)return 'Setting';return out.charAt(0).toUpperCase()+out.slice(1)}
function plainError(message){
 const text=String(message||'');
 if(text==='Enter a number')return 'Enter a number in that box.';
 if(text==='That grouped setting is not written correctly.')return text;
 if(/rejected|Check input|JSON|not usable/i.test(text))return 'One of those settings cannot be used. Change it, and the answer will try again.';
 if(/Invalid integration|Integration failed|Request failed/i.test(text))return 'This page could not finish the answer.';
 return text||'Something went wrong. Change a setting and try again.'}
function showValue(v){if(structured(v)&&!isFlat(v))return JSON.stringify(v,null,2);if(Array.isArray(v))return v.join(', ');return String(v)}
function readValue(raw,old){
 if(structured(old)&&!isFlat(old)){try{return JSON.parse(raw)}catch(e){throw Error('That grouped setting is not written correctly.')}}
 if(Array.isArray(old)){return raw.split(',').map(x=>{const t=x.trim();return typeof old[0]==='number'?Number(t):t}).filter(x=>x!==''&&!(typeof x==='number'&&Number.isNaN(x)))}
 if(typeof old==='number'){if(String(raw).trim()===''||Number.isNaN(Number(raw)))throw Error('Enter a number');return Number(raw)}
 if(typeof old==='boolean')return raw==='true';return raw}
function onEdit(){try{sync();el('error').textContent='';clearTimeout(timer);timer=setTimeout(()=>el('run').click(),300)}catch(e){el('error').textContent=plainError(e.message);el('status').textContent='Needs a change'}}
function fieldValue(node,old){
 if(node.type==='checkbox'&&node.dataset.kind!=='records'&&node.dataset.kind!=='flat')return node.checked;
 if(node.dataset.kind==='records'){const rows=[];node.querySelectorAll('.record').forEach(card=>{const row={};card.querySelectorAll('[data-col]').forEach(input=>{const sample=old[0]?old[0][input.dataset.col]:'';row[input.dataset.col]=input.type==='checkbox'?input.checked:readValue(input.value,sample)});rows.push(row)});return rows}
 if(node.dataset.kind==='flat'){const obj={};node.querySelectorAll('[data-part]').forEach(input=>{const sample=old[input.dataset.part];obj[input.dataset.part]=input.type==='checkbox'?input.checked:readValue(input.value,sample)});return obj}
 return readValue(node.value,old)}
function sync(){const p={};document.querySelectorAll('#controls [data-key]').forEach(node=>{p[node.dataset.key]=fieldValue(node,example[node.dataset.key])});el('input').value=JSON.stringify(p,null,2)}
function hint(text){const p=document.createElement('p');p.className='hint';p.textContent=text;return p}
function yesNo(v){const s=document.createElement('span');s.className=v?'yes':'no';s.textContent=v?'Yes':'No';return s}
function paintSwitch(input,state){state.textContent=input.checked?'On':'Off'}
function records(key,rows){
 const wrap=document.createElement('div');wrap.dataset.key=key;wrap.dataset.kind='records';wrap.className='group';
 wrap.append(hint('Each item is one group. Change a box, add another, or remove one.'));
 const cols=Object.keys(rows[0]||{});const list=document.createElement('div');
 function add(row){const card=document.createElement('div');card.className='record';cols.forEach(c=>{const lab=document.createElement('label');lab.className='field';lab.append(document.createTextNode(label(c)));const sample=rows[0][c];const input=document.createElement('input');input.dataset.col=c;if(typeof sample==='boolean'){input.type='checkbox';input.checked=!!row[c];input.onchange=onEdit}else{input.value=row[c]==null?'':String(row[c]);input.oninput=onEdit}lab.append(input);card.append(lab)});const rm=document.createElement('button');rm.type='button';rm.className='remove';rm.textContent='Remove';rm.onclick=()=>{card.remove();onEdit()};card.append(rm);list.append(card)}
 rows.forEach(add);
 const addBtn=document.createElement('button');addBtn.type='button';addBtn.className='add';addBtn.textContent='Add another';addBtn.onclick=()=>{const blank={};cols.forEach(c=>{const sample=rows[0][c];blank[c]=typeof sample==='number'?0:typeof sample==='boolean'?false:''});add(blank);onEdit()};
 wrap.append(list,addBtn);return wrap}
function dataTable(rows){
 const table=document.createElement('table');const cols=Object.keys(rows[0]||{});const head=document.createElement('tr');
 cols.forEach(c=>{const th=document.createElement('th');th.textContent=label(c);head.append(th)});
 const thead=document.createElement('thead');thead.append(head);const body=document.createElement('tbody');
 rows.forEach(row=>{const tr=document.createElement('tr');cols.forEach(c=>{const td=document.createElement('td');const cell=row[c];if(typeof cell==='boolean')td.append(yesNo(cell));else td.textContent=cell&&typeof cell==='object'?JSON.stringify(cell):String(cell??'');tr.append(td)});body.append(tr)});
 table.append(thead,body);return table}
function checks(obj){const ul=document.createElement('ul');ul.className='checks';Object.entries(obj).forEach(([k,v])=>{const li=document.createElement('li');const name=document.createElement('span');name.textContent=label(k);li.append(name,yesNo(v));ul.append(li)});return ul}
function names(list){const ul=document.createElement('ul');ul.className='names';list.forEach(item=>{const li=document.createElement('li');li.textContent=String(item);ul.append(li)});return ul}
function show(value,parent){
 if(Array.isArray(value)){parent.append(isNames(value)?names(value):names(value.map(x=>x&&typeof x==='object'?JSON.stringify(x):String(x))));return}
 if(isChecks(value)){parent.append(checks(value));return}
 if(value&&typeof value==='object'){const table=document.createElement('table');Object.entries(value).forEach(([k,v])=>{const row=table.insertRow(),key=row.insertCell(),cell=row.insertCell();key.textContent=label(k);if(typeof v==='boolean')cell.append(yesNo(v));else if(v&&typeof v==='object')show(v,cell);else cell.textContent=String(v??'')});parent.append(table);return}
 const p=document.createElement('p');p.textContent=String(value);parent.append(p)}
function flat(key,obj){
 const wrap=document.createElement('fieldset');wrap.dataset.key=key;wrap.dataset.kind='flat';wrap.className='group';
 const legend=document.createElement('legend');legend.textContent=label(key);wrap.append(legend,hint('Each box is one part of this setting.'));
 Object.entries(obj).forEach(([part,value])=>{const lab=document.createElement('label');lab.className=typeof value==='boolean'?'switch':'field';const name=document.createTextNode(label(part));const input=document.createElement('input');input.dataset.part=part;if(typeof value==='boolean'){input.type='checkbox';input.checked=value;const state=document.createElement('span');state.className='state';input.onchange=()=>{paintSwitch(input,state);onEdit()};lab.append(input,name,state);paintSwitch(input,state)}else{input.value=value==null?'':String(value);input.oninput=onEdit;lab.append(name,input)}wrap.append(lab)});
 return wrap}
function scalar(key,value){
 if(typeof value==='boolean'){const lab=document.createElement('label');lab.className='switch';const input=document.createElement('input');input.type='checkbox';input.dataset.key=key;input.checked=value;const state=document.createElement('span');state.className='state';input.onchange=()=>{paintSwitch(input,state);onEdit()};lab.append(input,document.createTextNode(label(key)),state);paintSwitch(input,state);return lab}
 const lab=document.createElement('label');lab.className='field';lab.append(document.createTextNode(label(key)));
 if(structured(value)&&!isFlat(value))lab.append(hint('This setting has several parts. Edit it as shown, or leave it as it is.'));
 const input=document.createElement(structured(value)&&!isFlat(value)||typeof value==='string'&&value.length>80?'textarea':'input');
 input.dataset.key=key;input.value=showValue(value);input.oninput=onEdit;lab.append(input);return lab}
function controls(){
 const box=el('controls');box.replaceChildren();const h=document.createElement('h2');h.textContent='Your settings';box.append(h);
 const keys=Object.keys(example);
 if(!keys.length){box.append(hint('This page has no settings to change. The answer is already based on the two repositories.'));return}
 keys.forEach(k=>{const v=example[k];if(isRecords(v)){const title=document.createElement('h3');title.textContent=label(k);box.append(title,records(k,v));return}if(isFlat(v)){box.append(flat(k,v));return}box.append(scalar(k,v))})}
function guide(){
 const list=el('guide');list.replaceChildren();
 const lines=['Change a setting on the left. The answer on the right updates by itself.','Read the answer on the right. When a highlighted sentence is there, it tells you what the result means.'];
 Object.entries(example).forEach(([k,v])=>{const name=label(k);if(isRecords(v))lines.push(name+' is a list of items. Change a box, add another, or remove one.');else if(isFlat(v))lines.push(name+' is a group of related settings. Each box is one part.');else if(typeof v==='boolean')lines.push(name+' is a switch. On and off give different answers.');else if(typeof v==='number')lines.push(name+' is a number. A different number gives a different answer.');else if(typeof v==='string')lines.push(name+' is text this page reads.');else if(Array.isArray(v))lines.push(name+' is a list. Separate items with commas.')});
 lines.forEach(text=>{const li=document.createElement('li');li.textContent=text;list.append(li)})}
function docs(obj){const wrap=document.createElement('div');const pre=document.createElement('pre');Object.keys(obj).forEach((name,i)=>{const b=document.createElement('button');b.type='button';b.className='page'+(i?'':' on');b.textContent=label(name);b.onclick=()=>{wrap.querySelectorAll('button.page').forEach(x=>x.classList.remove('on'));b.classList.add('on');pre.textContent=String(obj[name]||'')};if(!i)pre.textContent=String(obj[name]||'');wrap.append(b)});wrap.append(pre);return wrap}
function showView(id){document.querySelectorAll('.view').forEach(v=>v.classList.toggle('on',v.id===id));document.querySelectorAll('#pages button').forEach(b=>b.classList.toggle('on',b.dataset.view===id))}
function addPage(id,title,node){
 node.id=id;node.className='view';el('views').append(node);
 if(!el('pages').querySelector('[data-view="view-results"]')){const home=document.createElement('button');home.type='button';home.className='page on';home.dataset.view='view-results';home.textContent='Your answer';home.onclick=()=>showView('view-results');el('pages').append(home)}
 const b=document.createElement('button');b.type='button';b.className='page';b.dataset.view=id;b.textContent=title;b.onclick=()=>showView(id);el('pages').append(b)}
function board(){
 const views=el('views');views.replaceChildren();el('pages').replaceChildren();
 const overview=document.createElement('section');overview.id='view-results';overview.className='view on';
 const h=document.createElement('h2');h.textContent='Your answer';const empty=document.createElement('p');empty.id='empty';empty.className='hint';empty.textContent='Working out the answer.';
 const metrics=document.createElement('div');metrics.id='metrics';metrics.className='metrics';const out=document.createElement('div');out.id='results';
 overview.append(h,empty,metrics,out);views.append(overview)}
function sectionBlock(title,text){const block=document.createElement('section');const h=document.createElement('h3');h.textContent=title;block.append(h);if(text)block.append(hint(text));return block}
function renderResult(value){
 board();el('empty').hidden=true;
 if(!value||typeof value!=='object'||Array.isArray(value)){show(value,el('results'));showView('view-results');return}
 const leads=[],rest=[];Object.entries(value).forEach(([k,v])=>{if(isLead(k,v))leads.push(v);else rest.push([k,v])});
 if(leads.length){const box=document.createElement('div');box.className='callout';const h=document.createElement('h3');h.textContent='What this means';box.append(h);leads.forEach(v=>{const p=document.createElement('p');p.textContent=v;box.append(p)});el('results').append(box)}
 else el('results').append(hint('The sections below are the answer for the settings on the left.'));
 const numbers=rest.filter(([,v])=>typeof v==='number'&&Number.isFinite(v));
 numbers.forEach(([k,v])=>{const card=document.createElement('div');card.className='metric';const name=document.createElement('span');name.textContent=label(k);const num=document.createElement('strong');if(numbers.length===1||k==='score')num.className='hero';num.textContent=String(v);const cap=document.createElement('small');cap.textContent='Calculated from your settings.';card.append(name,num,cap);el('metrics').append(card)});
 rest.forEach(([k,v])=>{
  if(typeof v==='number'&&Number.isFinite(v))return;
  if(isRecords(v)){const block=sectionBlock(label(k),'Each row is one answer. Compare the columns from left to right.');block.append(dataTable(v));el('results').append(block);return}
  if(isChecks(v)){const block=sectionBlock(label(k),'Yes means that check matched. No means it did not.');block.append(checks(v));el('results').append(block);return}
  if(isDocs(v)){const section=document.createElement('section');const h=document.createElement('h2');h.textContent=label(k);section.append(h,hint('This is longer text the page prepared. Pick a part to read it.'),docs(v));addPage('view-'+k,label(k),section);const block=sectionBlock(label(k),'Open '+label(k)+' above when you want the longer write-up.');el('results').append(block);return}
  if(isNames(v)){const block=sectionBlock(label(k),'These names are part of the answer.');block.append(names(v));el('results').append(block);return}
  if(typeof v==='string'){const block=sectionBlock(label(k),'');const p=document.createElement('p');p.textContent=v;block.append(p);el('results').append(block);return}
  const block=sectionBlock(label(k),'These details belong together.');show(v,block);el('results').append(block)});
 showView('view-results')}
async function execute(){el('error').textContent='';el('status').textContent='Updating';el('run').disabled=true;try{sync();const payload=JSON.parse(el('input').value);const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');el('output').textContent=JSON.stringify(d,null,2);renderResult(d.result);el('status').textContent='Up to date'}catch(e){el('error').textContent=plainError(e.message);el('status').textContent='Needs a change'}finally{el('run').disabled=false}}
async function init(){try{const r=await fetch('/api/describe');const d=await r.json();if(!r.ok)throw Error(d.error);el('title').textContent=d.title;document.title=d.title;el('description').textContent=d.description;example=d.example&&typeof d.example==='object'?d.example:{};el('input').value=JSON.stringify(example,null,2);guide();controls();board();await execute()}catch(e){el('error').textContent=plainError(e.message);el('status').textContent='Needs a change'}}
el('run').onclick=execute;init();
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
