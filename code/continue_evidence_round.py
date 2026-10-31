"""Resume completed training with checks, scoring and report; no retraining."""
import os,subprocess,sys,json,time
from pathlib import Path
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
out=Path('runs/evidence_round')
assert (out/'freeze.json').exists(),'Training not frozen; inspect evidence-training.log'
for args in [['check_evidence_round.py'],['run_evidence_round.py','--stage','evaluate'],['report_evidence_round.py']]:
    print('START '+json.dumps(args),flush=True)
    subprocess.run([sys.executable,'-X','utf8','-B',*args],check=True)
print('ALL EVIDENCE TASKS COMPLETE',flush=True)
