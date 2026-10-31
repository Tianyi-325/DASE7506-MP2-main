"""Sequential supplementary controls, uncontended resource recheck and final integrity."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import subprocess,sys,json,time,hashlib,zipfile
from pathlib import Path
from run_fusion_experiments import official,save,digest
out=Path('runs/evidence_round')
subprocess.run([sys.executable,'-X','utf8','-B','supplement_evidence_controls.py','--stage','evaluate'],check=True)
# Freeze-control preparation briefly overlapped the main scoring loop.
# Re-measure only evaluation intervals that intersected that preparation.
start=Path('supplement_evidence_controls.py').stat().st_mtime-1
end=(out/'unit-controls-freeze.json').stat().st_mtime+1
r=json.loads((out/'official-results.json').read_text(encoding='utf8'));remeasured=[]
for n,splits in r.items():
    for split,v in list(splits.items()):
        file=out/'official'/n/(split+'-score.json')
        finish=file.stat().st_mtime
        begin=finish-v['fresh_prediction_plus_scoring_seconds']
        if finish>=start and begin<=end:
            score,_=official(out/'official',n,'evidence_models.py',out/'variants'/n/'model_bundle',split)
            assert score['correct']==v['correct']
            remeasured.append({'variant':n,'split':split,'previous_seconds':v['fresh_prediction_plus_scoring_seconds'],'new_seconds':score['fresh_prediction_plus_scoring_seconds']})
            r[n][split]=score
save(out/'official-results.json',r)
save(out/'resource-remeasurement.json',{'reason':'Remove overlap with supplementary control freeze preparation; fixed models unchanged','records':remeasured})
com=json.loads((out/'compliance.json').read_text(encoding='utf8'))
units=json.loads((out/'unit-controls-results.json').read_text(encoding='utf8'))
com['max_test_fresh_seconds']=max(v['test']['fresh_prediction_plus_scoring_seconds'] for v in [*r.values(),*units.values()])
com['additional_unit_controls']=2;save(out/'compliance.json',com)
manifest=json.loads(Path('PACKAGE_MANIFEST.json').read_text(encoding='utf8'));changed=[]
for p,h in manifest['files'].items():
    if digest(Path('..')/p)!=h:changed.append(p)
assert not changed,changed
freeze=json.loads((out/'freeze.json').read_text(encoding='utf8'))
for p,h in freeze['source_sha256'].items():assert digest(Path(p))==h
for n,v in freeze['variants'].items():
    bundle=out/'variants'/n/'model_bundle'
    assert sum(p.stat().st_size for p in bundle.iterdir())==v['asset_bytes']
    for p,h in v['assets'].items():assert digest(bundle/p)==h
    for p in bundle.glob('*.npz'):
        with zipfile.ZipFile(p) as z:assert all(x.compress_type==zipfile.ZIP_STORED for x in z.infolist())
assert com['max_test_fresh_seconds']<30 and com['max_asset_bytes']<16*2**20
save(out/'all-python-sources.json',{p.name:digest(p) for p in sorted(Path('.').glob('*.py'))})
save(out/'final-integrity.json',{'official_package_files_unchanged':len(manifest['files']),'frozen_main_variants':len(r),
  'unit_controls':len(units),'all_frozen_sources_and_assets_passed':True,'uncompressed_asset_sizes_passed':True,
  'no_method_or_selection_changes_after_test':True,'resources_local_passed':True,'reference_Xeon_not_measured':True})
subprocess.run([sys.executable,'-X','utf8','-B','report_evidence_round.py'],check=True)
print('FINAL EVIDENCE ROUND COMPLETE',flush=True)
