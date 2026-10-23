"""Refresh the offline rules snapshot from the fixed public Skill repository."""
import urllib.request,urllib.parse,json,hashlib,concurrent.futures
from pathlib import Path
base='https://api.github.com/repos/shengjidaguai-china/goutoujunshi'
def get(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'goutou-rule-bundler'}),timeout=40) as r:return r.read()
sha=json.loads(get(base+'/commits/main'))['sha']
tree=json.loads(get(base+'/git/trees/'+sha+'?recursive=1'))
assert not tree.get('truncated')
rows=[x for x in tree['tree'] if x['type']=='blob' and (x['path']=='SKILL.md' or x['path'].startswith('references/') and x['path'].endswith('.md'))]
def load(row):
 raw=get('https://raw.githubusercontent.com/shengjidaguai-china/goutoujunshi/'+sha+'/'+urllib.parse.quote(row['path']))
 assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==row['sha']
 return row['path'],raw.decode('utf-8'),row['sha']
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool: docs=list(pool.map(load,rows))
pack={'schema':1,'revision':sha,'documents':{p:t for p,t,h in docs},'hashes':{p:h for p,t,h in docs}}
p=Path(__file__).resolve().parents[1] / 'RuleResources';p.mkdir(exist_ok=True)
(p/'SkillRules-LICENSE.txt').write_bytes(get('https://raw.githubusercontent.com/shengjidaguai-china/goutoujunshi/'+sha+'/LICENSE'))
(p/'SkillRules.json').write_text(json.dumps(pack,ensure_ascii=False,sort_keys=True),encoding='utf-8')
print(sha,len(docs),'documents',sum(len(t.encode()) for p,t,h in docs),'bytes')
