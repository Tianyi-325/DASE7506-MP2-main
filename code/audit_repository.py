"""Read-only repository audit; inventory does not contain benchmark question text."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import ast,hashlib,json,time,zipfile,re,sys
from pathlib import Path
from collections import Counter
from urllib.parse import unquote
import numpy as np
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'code/runs/repository_audit'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def main():
    started=time.perf_counter();paths=sorted(p for p in ROOT.rglob('*') if p.is_file() and OUT not in p.parents and p != ROOT/'code/repository-audit.log')
    inventory=[];failures=[];links=[];logs=[];counts=Counter();array_count=0;jsonl_count=0
    for i,p in enumerate(paths):
        rel=p.relative_to(ROOT).as_posix();b=p.read_bytes();ext=p.suffix.lower();counts[ext]+=1
        r={'path':rel,'bytes':len(b),'sha256':sha(b)}
        try:
            if ext in ('.npz','.npy'):
                if ext=='.npz':
                    with zipfile.ZipFile(p) as z:assert z.testzip() is None
                    with np.load(p,allow_pickle=False) as z:
                        keys=z.files;r['arrays']=len(keys)
                        for k in keys:
                            a=z[k];array_count+=1
                            if np.issubdtype(a.dtype,np.inexact):assert np.isfinite(a).all(),('nonfinite',k)
                else:
                    a=np.load(p,allow_pickle=False);array_count+=1
                    if np.issubdtype(a.dtype,np.inexact):assert np.isfinite(a).all()
                    r['shape']=list(a.shape);r['dtype']=str(a.dtype)
            elif ext!='.pyc':
                try:s=b.decode('utf-8-sig')
                except UnicodeDecodeError:
                    if ext!='.log':raise
                    s=b.decode('gb18030');r['text_encoding']='gb18030 (historical Windows log)' 
                if ext=='.py':ast.parse(s,filename=rel)
                elif ext=='.json':json.loads(s)
                elif ext=='.jsonl':
                    n=0
                    for line in s.split('\n'):
                        if line.strip():json.loads(line);n+=1
                    r['rows']=n;jsonl_count+=n
                elif ext=='.md':
                    for m in re.finditer(r'\]\(([^)]+)\)',s):
                        t=m.group(1).split('#')[0].strip('<>')
                        if not t or re.match(r'^[a-zA-Z][\w+.-]*:',t):continue
                        t=unquote(t)
                        if not (p.parent/t).exists():links.append({'file':rel,'target':t})
                elif ext=='.log':
                    tokens={k:s.count(k) for k in ('Traceback','SyntaxError','AssertionError','ERROR','FileNotFoundError') if k in s}
                    if tokens:logs.append({'file':rel,'historical_error_token_counts':tokens,'not_current_failure_proof':True})
        except Exception as e:failures.append({'path':rel,'error':str(e)})
        inventory.append(r)
        if i%500==0:print(json.dumps({'checked':i,'total':len(paths)}),flush=True)
    package=load(ROOT/'code/PACKAGE_MANIFEST.json')
    original=[{'path':p,'passed':sha((ROOT/p).read_bytes())==h} for p,h in package['files'].items()]
    f=load(ROOT/'code/runs/evidence_round/freeze.json');tracked=[]
    for p,h in f['source_sha256'].items():tracked.append({'path':'code/'+p,'passed':sha((ROOT/'code'/p).read_bytes())==h})
    bundle=ROOT/'code/runs/evidence_round/variants/joint_residual_relative_r3/model_bundle'
    for p,h in f['variants']['joint_residual_relative_r3']['assets'].items():tracked.append({'path':str((bundle/p).relative_to(ROOT)),'passed':sha((bundle/p).read_bytes())==h})
    # Parse import graph without importing training modules or running their code.
    modules={p.stem:p for p in (ROOT/'code').glob('*.py')}
    pending=['evidence_models'];seen=set();external=set()
    while pending:
        n=pending.pop()
        if n in seen:continue
        seen.add(n);tree=ast.parse(modules[n].read_text(encoding='utf8'))
        for node in ast.walk(tree):
            imports=[]
            if isinstance(node,ast.Import):imports=[x.name.split('.')[0] for x in node.names]
            elif isinstance(node,ast.ImportFrom) and node.module:imports=[node.module.split('.')[0]]
            for k in imports:
                if k in modules:pending.append(k)
                else:external.add(k)
    # Re-score the existing frozen output; no re-training and no new model selection.
    from common import score_choices
    pred=load(ROOT/'code/runs/evidence_round/official/joint_residual_relative_r3/test-predictions.json')
    score=score_choices('test',pred['ids'],pred['selected'])
    oldscore=load(ROOT/'code/runs/evidence_round/official/joint_residual_relative_r3/test-score.json')
    assert score['correct']==oldscore['correct']==401 and score['n']==467
    summary={'scope':'All regular files present at audit start, excluding audit output directory and its live log; original files not edited',
      'files_checked':len(paths),'bytes_checked':sum(r['bytes'] for r in inventory),'counts':dict(counts),
      'array_members_checked':array_count,'jsonl_rows_parsed':jsonl_count,'file_failures':failures,
      'missing_markdown_link_targets':links,'logs_with_historical_error_tokens':logs,
      'original_package_files':original,'final_frozen_sources_and_assets':tracked,
      'final_B_existing_predictions_official_rescore':score,
      'B_local_inference_source_closure':[str(modules[n].relative_to(ROOT)).replace('\\','/') for n in sorted(seen)],
      'B_external_import_roots':sorted(external),'dependencies_not_dynamic_execution_proof':True,
      'git_metadata_present':(ROOT/'.git').exists(),
      'gitignore_ignores_runs':bool(re.search(r'^runs/$',(ROOT/'.gitignore').read_text(encoding='utf8'),re.M)),
      'formal_pdf_docx_files':[str(p.relative_to(ROOT)) for p in paths if p.suffix.lower() in ('.pdf','.docx')],
      'elapsed_seconds':time.perf_counter()-started,'not_clean_environment_reproduction':True,'no_external_submission_checked':True}
    save(OUT/'file-inventory.json',inventory);save(OUT/'audit-results.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('original_package_files','final_frozen_sources_and_assets','logs_with_historical_error_tokens')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
