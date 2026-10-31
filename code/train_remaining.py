"""Train the three remaining directions with fixed, bounded validation searches."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[k]='4'
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch
from torch import nn
from common import load_inputs
from train_vector import labels
from train_objectives import group_loss
from run_fusion_experiments import save
from vector_vote_fusion import select_from_scores
from reasoning_features import extract_features,relations,TEXT_NAMES,CALC_NAMES
from remaining_models import scores_with_assets

FAMILIES={
 'linear_control':('linear','none'), 'linear_text':('linear','text'),
 'linear_calc':('linear','calc'), 'linear_textcalc':('linear','textcalc'),
 'mlp':('mlp','none'), 'context':('context','none'), 'context_textcalc':('context','textcalc')}


class Scorer(nn.Module):
    def __init__(self,dims,architecture,hidden):
        super().__init__();self.architecture=architecture
        if architecture=='linear':
            self.linear=nn.Linear(dims,1,bias=False)
            nn.init.zeros_(self.linear.weight)
        else:
            self.encoder=nn.Linear(dims,hidden)
            self.dropout=nn.Dropout(0.1)
            if architecture=='context': self.context=nn.Linear(5*hidden+1,hidden)
            self.output=nn.Linear(hidden,1)
    def forward(self,x,same,votes):
        if self.architecture=='linear': return self.linear(x).squeeze(-1)
        h=self.dropout(torch.relu(self.encoder(x)))
        if self.architecture=='context':
            group=h.mean(dim=1,keepdim=True).expand_as(h)
            own=torch.bmm(same,h)
            h=self.dropout(torch.relu(self.context(torch.cat([h,group,h-group,own,h-own,votes],dim=-1))))
        return self.output(h).squeeze(-1)


def export(model):
    def value(t): return t.detach().numpy().copy()
    if model.architecture=='linear':
        return {'linear_weight':value(model.linear.weight).T,'linear_bias':np.zeros(1,dtype=np.float32)}
    result={'encoder_weight':value(model.encoder.weight).T,'encoder_bias':value(model.encoder.bias),
            'output_weight':value(model.output.weight).T,'output_bias':value(model.output.bias)}
    if model.architecture=='context':
        result.update({'context_weight':value(model.context.weight).T,'context_bias':value(model.context.bias)})
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('runs/remaining_directions'))
    args=parser.parse_args();out=args.output
    if (out/'freeze.json').exists(): raise FileExistsError('Use a new output directory')
    torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    started=time.perf_counter()
    bank,arrays=load_inputs('train');vb,va=load_inputs('validation')
    y=labels('train',bank);vy=labels('validation',vb);target=torch.from_numpy(y);vt=torch.from_numpy(vy)
    raw=arrays['embeddings'];mean=raw.reshape(-1,1024).mean(axis=0,dtype=np.float64).astype(np.float32)
    scale=np.maximum(raw.reshape(-1,1024).std(axis=0,dtype=np.float64).astype(np.float32),1e-6)
    embedding=(raw-mean)/scale;ve=(va['embeddings']-mean)/scale
    same,votes=map(torch.from_numpy,relations(bank));vsame,vvotes=map(torch.from_numpy,relations(vb))
    all_records=[];curves=[];selected={};replicas={};variants={}
    preprocessing={}
    for kind in ('none','text','calc','textcalc'):
        tr=extract_features(bank,kind);val=extract_features(vb,kind)
        if kind=='none': fm=np.zeros(0,np.float32);fs=np.ones(0,np.float32)
        else:
            fm=tr.reshape(-1,tr.shape[-1]).mean(axis=0,dtype=np.float64).astype(np.float32)
            fs=np.maximum(tr.reshape(-1,tr.shape[-1]).std(axis=0,dtype=np.float64).astype(np.float32),1e-6)
        preprocessing[kind]={'feature_mean':fm,'feature_scale':fs,
            'x':torch.from_numpy(np.concatenate([embedding,(tr-fm)/fs],axis=-1)),
            'vx':torch.from_numpy(np.concatenate([ve,(val-fm)/fs],axis=-1))}
    for family,(architecture,kind) in FAMILIES.items():
        prep=preprocessing[kind];x=prep['x'];vx=prep['vx'];best=None
        configurations=([{'hidden':0,'regularization':r,'lr':0.03} for r in ([0.001] if family=='linear_control' else [0.001,0.01])]
            if architecture=='linear' else [{'hidden':32,'regularization':0.001,'lr':0.001},{'hidden':64,'regularization':0.01,'lr':0.001}])
        checkpoints=(120,360,720) if architecture=='linear' else (20,40,80)
        for config in configurations:
            torch.manual_seed(2026)
            model=Scorer(x.shape[-1],architecture,config['hidden'])
            optimizer=(torch.optim.Adam(model.parameters(),lr=config['lr']) if architecture=='linear' else
                       torch.optim.AdamW(model.parameters(),lr=config['lr'],weight_decay=config['regularization']))
            tick=time.perf_counter()
            for epoch in range(1,max(checkpoints)+1):
                model.train();training_sum=0.
                order=torch.arange(len(bank)) if architecture=='linear' else torch.randperm(len(bank))
                batch_size=len(bank) if architecture=='linear' else 256
                for index in order.split(batch_size):
                    optimizer.zero_grad(set_to_none=True)
                    logits=model(x[index],same[index],votes[index])
                    loss=group_loss(logits,target[index])
                    if architecture=='linear': loss=loss+0.5*config['regularization']*model.linear.weight.square().sum()
                    loss.backward();optimizer.step()
                    training_sum+=float(loss.detach())*len(index)
                if epoch==1 or epoch%10==0:
                    curves.append({'family':family,'config':config,'seed':2026,'epoch':epoch,'training_objective_epoch_mean':training_sum/len(bank)})
                if epoch not in checkpoints: continue
                model.eval()
                with torch.no_grad():
                    logits=model(vx,vsame,vvotes);vl=float(group_loss(logits,vt));vals=logits.numpy()
                counts={mode:int(vy[np.arange(len(vb)),select_from_scores(vb,vals,mode,alpha)].sum()) for mode,alpha in [('valid_only',0.),('weighted',0.25)]}
                record={'family':family,'architecture':architecture,'features':kind,'config':config,'seed':2026,'epoch':epoch,
                        'validation_correct':counts,'validation_group_loss':vl,'trajectory_seconds':time.perf_counter()-tick}
                all_records.append(record)
                rank=(counts['valid_only'],-vl)
                if best is None or rank>best['rank']: best={'rank':rank,'record':record,'arrays':export(model)}
                save(out/'progress.json',{'latest':record,'completed_checkpoints':len(all_records)})
                print(json.dumps(record),flush=True)
        selected[family]=best['record']
        if architecture!='linear':
            # One prespecified replication of the selected setup; not a new search.
            config=best['record']['config'];torch.manual_seed(2027)
            replica=Scorer(x.shape[-1],architecture,config['hidden'])
            optimizer=torch.optim.AdamW(replica.parameters(),lr=config['lr'],weight_decay=config['regularization'])
            for epoch in range(best['record']['epoch']):
                replica.train()
                for index in torch.randperm(len(bank)).split(256):
                    optimizer.zero_grad(set_to_none=True)
                    loss=group_loss(replica(x[index],same[index],votes[index]),target[index]);loss.backward();optimizer.step()
            replica.eval()
            with torch.no_grad(): logits=replica(vx,vsame,vvotes).numpy()
            replicas[family]={'seed':2027,'epoch':best['record']['epoch'],'validation_correct':{
                mode:int(vy[np.arange(len(vb)),select_from_scores(vb,logits,mode,alpha)].sum()) for mode,alpha in [('valid_only',0.),('weighted',0.25)]},
                'policy':'diagnostic only; original seed 2026 retained irrespective of replication result'}
            save(out/family/'replication-2027.json',replicas[family])
            np.savez(out/family/'replication-2027-weights.npz',**export(replica))
        assets={'embedding_mean':mean,'embedding_scale':scale,'feature_mean':prep['feature_mean'],'feature_scale':prep['feature_scale'],**best['arrays']}
        for mode,alpha in [('valid_only',0.),('weighted',0.25)]:
            name=family+'_'+mode;bundle=out/name/'model_bundle';bundle.mkdir(parents=True,exist_ok=True)
            config={'family':family,'architecture':architecture,'features':kind,'mode':mode,'alpha':alpha,
                    'training':best['record'],'selection':'valid_only validation count, then group loss; seed2026 only',
                    'feature_names':(TEXT_NAMES if kind=='text' else CALC_NAMES if kind=='calc' else TEXT_NAMES+CALC_NAMES if kind=='textcalc' else []),
                    'standardization':'train-only','inference':'numpy','torch_training':torch.__version__,'numpy':np.__version__}
            np.savez(bundle/'model.npz',**assets);save(bundle/'config.json',config)
            vals=scores_with_assets(vb,va,config,assets)
            choices=select_from_scores(vb,vals,mode,alpha);count=int(vy[np.arange(len(vb)),choices].sum())
            assert count==best['record']['validation_correct'][mode],(name,count,best['record'])
            variants[name]={'validation_correct':count,'assets':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(bundle.iterdir())},
                            'asset_bytes':sum(p.stat().st_size for p in bundle.iterdir())}
    sources=('train_remaining.py','evaluate_remaining.py','remaining_models.py','reasoning_features.py','train_objectives.py',
             'train_vector.py','vector_vote_fusion.py','vector_logistic.py','run_fusion_experiments.py','check_remaining.py')
    save(out/'freeze.json',{'selected':selected,'variants':variants,'source_sha256':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in sources},
         'test_policy':'No test read during training/selection; fixed alpha 0.25 for all families',
         'validation_preferred_variant':max(variants,key=lambda n:variants[n]['validation_correct'])})
    save(out/'training-results.json',{'checkpoints':all_records,'curves':curves,'replications':replicas,
         'search_and_replication_seconds_excluding_startup_imports':time.perf_counter()-started,'device':'cpu','threads':4,
         'linear_checkpoints':[120,360,720],'neural_checkpoints':[20,40,80],
         'notes':'NN training objective uses dropout and weight decay, linear uses explicit L2; their training loss numbers are not directly comparable.'})
    print(json.dumps({'frozen':True,'validation_counts':{n:v['validation_correct'] for n,v in variants.items()}}),flush=True)


if __name__=='__main__': main()
