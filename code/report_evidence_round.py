"""Post-freeze descriptive report; never changes selection or assets."""
import argparse,json,hashlib,sys
from pathlib import Path
import numpy as np
from common import load_inputs
from run_fusion_experiments import labels
from math_evidence import equations
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def main(out):
    f=json.loads((out/'freeze.json').read_text(encoding='utf8'));sel=json.loads((out/'selection.json').read_text(encoding='utf8'))
    res=json.loads((out/'official-results.json').read_text(encoding='utf8'));comp=json.loads((out/'compliance.json').read_text(encoding='utf8'))
    checks=json.loads((out/'checks.json').read_text(encoding='utf8'));assert checks['passed'] and len(res)==len(f['variants'])
    bank,arrays=load_inputs('validation');y=labels(bank,'validation');del arrays
    co={};choices={}
    for n,r in res.items():
        assert set(r)=={'test','validation'}
        p=json.loads((out/'official'/n/'validation-predictions.json').read_text(encoding='utf8'))['selected']
        choices[n]=p;co[n]=y[np.arange(len(y)),p].astype(bool)
    with np.load(out/'development-correctness.npz',allow_pickle=False) as z:dev={k:z[k] for k in z.files}
    records=sel['records'];chosen=sel['selected'];inc=sel['incumbent']
    def best(names):return max(names,key=lambda n:(records[n]['mean_oof_correct'],records[n]['validation_correct'],n))
    module_best={b:best([n for n in records if ('_'+b+'_r') in n]) for b in ('semantic','verify','both','relative')}
    diag={}
    with np.load(out/'input-cache.npz',allow_pickle=False) as z:
        for split,prefix in [('train','t_'),('validation','v_')]:
            s=z[prefix+'semantic'];v=z[prefix+'verify'];r=z[prefix+'relative']
            diag[split]={'questions':len(s),'candidates':len(s)*4,
              'candidate_numeric_checked':int((v[:,:,0]>0).sum()),
              'candidate_numeric_wrong_flagged':int((v[:,:,1]>0).sum()),
              'candidate_unit_checked':int((v[:,:,8]>0).sum()),
              'candidate_unit_wrong_flagged':int((v[:,:,9]>0).sum()),
              'candidate_box_official_mismatch':int((v[:,:,11]>0).sum()),
              'candidate_terminal_official_mismatch':int((v[:,:,13]>0).sum()),
              'question_target_unit_known':int((s[:,:,5]>0).any(axis=1).sum()),
              'question_salient_factor_known':int((s[:,:,2]>0).any(axis=1).sum()),
              'nonconstant_features':[int((x.reshape(-1,x.shape[-1]).std(axis=0)>1e-8).sum()) for x in (s,v,r)]}
        vs=z['v_semantic'];vv=z['v_verify'];vr=z['v_relative']
        data={k[2:]:z[k] for k in z.files if k.startswith('t_')}
        for base in ('no_style','joint'):
            with np.load(out/'fits'/'full'/(base+'.npz'),allow_pickle=False) as a:
                from evidence_models import group_margin,member_scores
                old=member_scores(data,{'base':base,'mode':'control'},a)
                margins=group_margin(data,old)/float(a['base_score_scale'])
                avail=(data['verify'][:,:,0]>0).any(axis=1)|(data['semantic'][:,:,2]>0).any(axis=1)|(data['semantic'][:,:,5]>0).any(axis=1)
                diag['train'][base+'_gates']={str(t):int(((margins<=t)&avail).sum()) for t in (.5,1.)}
    save(out/'coverage.json',diag)
    errors=json.loads(Path('runs/residual_error_audit/annotated-errors.json').read_text(encoding='utf8'))
    manual=json.loads(Path('runs/residual_error_audit/manual-annotations.json').read_text(encoding='utf8'))
    residual={}
    for n in res:
        residual[n]={'fixed_prior51':sum(bool(co[n][r['position']]) for r in errors),
          'fixed_prior_shared36':sum(bool(co[n][r['position']]) and r['all_focused_models_wrong'] for r in errors),'by_manual_primary':{}}
        for kind in ('semantic','arithmetic','parser','ambiguous'):
            ids=[r['position'] for r in errors if manual[str(r['position'])][0]==kind]
            residual[n]['by_manual_primary'][kind]={'n':len(ids),'fixed':int(co[n][ids].sum())}
    save(out/'residual-validation-results.json',residual)
    rng=np.random.default_rng(20261101);boot={}
    for n in set([chosen,*module_best.values()]):
        delta=(dev['oof_'+n]-dev['oof_'+inc]).mean(axis=0)
        draws=np.array([delta[rng.integers(0,len(delta),len(delta))].sum() for _ in range(2000)])
        boot[n]={'mean_oof_gain':float(delta.sum()),'question_bootstrap_95pct_gain':np.quantile(draws,[.025,.975]).tolist(),'descriptive_only_after_search':True}
    save(out/'descriptive-bootstrap.json',boot)
    from evidence_training import SPECS
    cases=[]
    for n in set([chosen,*module_best.values()]):
        base=records[n]['parts'][0][0]
        base=SPECS.get(base,{}).get('base',inc)
        if base=='none':base=inc
        for direction,mask in [('fixed',co[n]&~co[base]),('broken',~co[n]&co[base])]:
            for i in np.flatnonzero(mask)[:5]:
                a,b=choices[base][i],choices[n][i]
                cases.append({'method':n,'base':base,'direction':direction,'position':int(i),'question':bank[i]['question'],
                  'old_choice':a,'new_choice':b,'correct_indices':np.flatnonzero(y[i]).tolist(),
                  'old_text':bank[i]['candidates'][a]['text'],'new_text':bank[i]['candidates'][b]['text'],
                  'old_evidence':{'semantic':vs[i,a].tolist(),'verify':vv[i,a].tolist(),'relative':vr[i,a].tolist()},
                  'new_evidence':{'semantic':vs[i,b].tolist(),'verify':vv[i,b].tolist(),'relative':vr[i,b].tolist()},
                  'warning':'Feature flags do not establish causality for a learned model switch.'})
    save(out/'validation-case-studies.json',cases)
    assert equations('2 hours + 30 minutes = 150 minutes')['unit_checked']==0
    assert equations('5 euros = 5 dollars')['unit_checked']==0
    fit_infos=list((out/'fits').glob('*/*.json'));fit_seconds=sum(json.loads(p.read_text(encoding='utf8'))['seconds'] for p in fit_infos)
    top_test=max(res,key=lambda n:res[n]['test']['correct']);top_val=max(res,key=lambda n:res[n]['validation']['correct'])
    lines=['# 第十轮：数学证据与旧模型融合','',
      f"41主配置、两套三折+全量287次主配置拟合、21次基础拟合、13组合，共{len(res)}冻结版本，均独立官方评分。",'',
      f"预定规则选择：{chosen}。验证{res[chosen]['validation']['correct']}/798；固定测试{res[chosen]['test']['correct']}/467={res[chosen]['test']['accuracy']:.4f}%。",
      f"旧参照：{inc}；晋级={sel['promoted']}；通过门槛={sel['eligible']}。测试在选模、权重和源码冻结后运行，不回流选型。",'',
      f"训练OOF选定组件：{json.dumps(sel['components'],ensure_ascii=False)}。",'',
      '## 核心对照','',
      '| 方法 | 两套OOF正确数/4755 | 相对参照种子增益 | 验证/798 | 固定测试/467 |',
      '|---|---|---|---:|---:|']
    core=list(dict.fromkeys(['no_style','joint','feature_selection','old_pair','old_triple',*module_best.values(),sel['components']['enhanced_joint'],chosen,*[n for n in records if n not in SPECS]]))
    def row(n):
        r=records[n]
        return f"| {n} | {r['oof_correct']} | {r['seed_gains']} | {res[n]['validation']['correct']} | {res[n]['test']['correct']} ({res[n]['test']['accuracy']:.4f}%) |"
    lines.extend(row(n) for n in core)
    lines+=['','模块代表按训练OOF选择，semantic=条件/目标，verify=局部检验，both=合并，relative=合并加相对证据。重训、固定主干残差和低分差限幅门控均有匹配参照。','',
      '## 结论的证据边界','',
      '晋级预设：平均OOF增益>=5题，两种子非负，六折至少四折正增益，最差折>=-6，验证不退步。所有逐折增益、匹配参照和修复/破坏见selection.json。此门槛不能视为显著性证明；OOF反复选模、复用验证集仍有选择偏差。',
      '描述性bootstrap按题重采样并保留同题两套预测，见descriptive-bootstrap.json；没有校正搜索选择，不作正式置信区间解释。',
      f"本轮最高验证记录{top_val}：{res[top_val]['validation']['correct']}/798；最高固定测试记录{top_test}：{res[top_test]['test']['correct']}/467。只报告记录，不据测试改选。此前最高固定测试391/467=83.7259%；85%需至少397题正确。",'',
      '## 原验证错题修复','',
      '| 方法 | 修复原51题 | 修复原36共同错题 | 语义类/41 | 算术类/7 |',
      '|---|---:|---:|---:|---:|']
    for n in list(dict.fromkeys([chosen,*module_best.values()])):
        r=residual[n];lines.append(f"| {n} | {r['fixed_prior51']} | {r['fixed_prior_shared36']} | {r['by_manual_primary']['semantic']['fixed']} | {r['by_manual_primary']['arithmetic']['fixed']} |")
    lines+=['','修复统计属于已有开发集分析；也必须考虑破坏原正确题。全部类别与方法见residual-validation-results.json，原文与切换证据见validation-case-studies.json。人工类别边界有重叠，仍以官方最终数值计分。','',
      '覆盖率是可计算特征的覆盖，不是逻辑检测准确率；最终答案标签不能验证每一步推理。有限语义规则不能解决所有对象、时间线、单位与指代问题。未知不等于正确，告警不等于最终错误。','',
      '覆盖记录：',json.dumps(diag,ensure_ascii=False,indent=2),'',
      '## 资源与完整性','',
      f"环境：Python {sys.version.split()[0]}，NumPy {np.__version__}，PyTorch {f['versions']['torch']}，Windows i9-12900H，CPU四线程，无GPU。",
      f"训练/冻结墙钟{f['elapsed_training_and_freezing_seconds']:.2f}秒；拟合计时合计{fit_seconds:.2f}秒（含基础拟合与控制导出，并非完整搜索墙钟）。",
      f"最大推理资产{comp['max_asset_bytes']}字节；最慢完整测试新预测+独立评分{comp['max_test_fresh_seconds']:.3f}秒；参考Xeon未实测。",
      f"所选模型资产{f['variants'][chosen]['asset_bytes']}字节，完整测试时间{res[chosen]['test']['fresh_prediction_plus_scoring_seconds']:.3f}秒。",
      '原数据hash、冻结源码/资产、三旧参照逐题复现、0/1/7题、候选重排、未知ID、无效候选fallback、NumPy推理和Torch导出一致性均通过。另验证混合尺度与跨货币表达式跳过。',
      '详见freeze.json、reference-parity.json、checks.json、compliance.json、official/。命令、软规则局限和AI/复用披露见../../EVIDENCE_EXPERIMENTS.md。无外部数据/权重、LLM调用或ID查表。','',
      '## 全部固定版本','',
      '| 变体 | 两套OOF正确数 | 增益 | 验证/798 | 固定测试/467 |','|---|---|---|---:|---:|']
    lines.extend(row(n) for n in records)
    if (out/'unit-controls-results.json').exists():
        units=json.loads((out/'unit-controls-results.json').read_text(encoding='utf8'))
        uf=json.loads((out/'unit-controls-freeze.json').read_text(encoding='utf8'))
        lines+=['','## 投票单位匹配的补充控制','',
          '两个控制在主选模已冻结之后声明，仅用于归因诊断，不回流选模。保留旧单模型权重，把训练分数标准差与alpha=.125对齐新组合。没有新增拟合。','',
          '| 控制 | 两套OOF正确数 | 验证/798 | 固定测试/467 |','|---|---|---:|---:|']
        for n,u in units.items():
            lines.append(f"| {n} | {uf['controls'][n]['oof_correct']} | {u['validation']['correct']} | {u['test']['correct']} |")
        selected_oof=np.asarray(records[chosen]['oof_correct'])
        matched=np.asarray(uf['controls']['normalized_no_style_control']['oof_correct'])
        lines+=['',f"主选定组合相对匹配去格式控制的OOF增益为{(selected_oof-matched).tolist()}；这可排查单纯分数单位/投票变化，但仍是同一开发搜索中的结果。"]
    lines+=['',f"所选版本是否达到85%：{res[chosen]['test']['correct']>=397}；本轮最高固定测试记录{res[top_test]['test']['accuracy']:.4f}%，是否达到85%：{res[top_test]['test']['correct']>=397}。最高记录不替代预先冻结的选择。",'', '## 各版本完整资源记录','', '| 变体 | 推理资产字节 | 新测试预测+评分秒 |', '|---|---:|---:|']
    for n in records:lines.append(f"| {n} | {f['variants'][n]['asset_bytes']} | {res[n]['test']['fresh_prediction_plus_scoring_seconds']:.3f} |")
    # Each module's best mean OOF variant compared with its own original backbone.
    matched_modules={}
    for b,n in module_best.items():
        base=SPECS[n]['base'];delta=dev['oof_'+n]-dev['oof_'+base]
        matched_modules[b]={'variant':n,'base':base,'seed_oof_gain':delta.sum(axis=1).tolist(),
          'validation_fixed':int((co[n]&~co[base]).sum()),'validation_broken':int((~co[n]&co[base]).sum()),
          'validation_gain':int(co[n].sum()-co[base].sum()),'test_records_only':{'method':res[n]['test']['correct'],'base':res[base]['test']['correct']}}
    save(out/'matched-module-comparisons.json',matched_modules)
    lines+=['','## 模块与自身旧主干的匹配比较','',
      '| 方向 | OOF代表 | 旧主干 | 两种子增益 | 验证修复/破坏 |','|---|---|---|---|---|']
    for b,r in matched_modules.items():
        lines.append(f"| {b} | {r['variant']} | {r['base']} | {r['seed_oof_gain']} | {r['validation_fixed']}/{r['validation_broken']} |")

    lines+=['','## 本轮分析结论','',
      '1. 相对证据是本轮最有一致支持的新增部分。相同去格式主干、冻结残差、L2=.03下，从both增加20维相对特征，两套OOF分别再多对8题、6题，验证748→750，固定测试390→398。相同joint主干则OOF再增6题、20题，验证747→751，固定测试394→401。这比跨主干挑最高分更能说明新增比较证据的价值。',
      '2. 条件/目标规则有开发集信号，但泛化收益不统一。OOF代表在两套划分增14/13题、验证修复3题且无破坏，固定测试却比自身旧主干少5题。局部检验代表OOF增10/17题，验证净增2题、固定测试增2题；其作用适合软证据，不能据此宣称已实现完整数学验证。',
      '3. 保留强主干并学习残差是有希望的用法。joint_residual_relative_r3保持旧向量主干，学习70维证据修正，验证751、测试401；去格式对应模型验证750、测试398。两者在各自主干内都由训练OOF选为增强组件；最高测试版本并非凭测试另调参数得到。',
      '4. 组合有帮助，但成员更多并不保证更好。新双模型75/25组合固定测试399，三模型395；旧双/三组合为389/388。全部是预定权重实验，不能把测试排序当成重新选权重的依据。',
      '5. 本轮选模存在明显不确定性。OOF最优合格组合no_style_evidence_90虽然OOF增25/32、验证751，测试389；匹配投票单位控制也是389，未看到其新增证据带来同步测试提升。最高验证755的版本测试394，也说明单一开发排名不能保证测试排名。',
      '6. 本轮确有冻结候选超过85%，最高401/467，相比旧391净增10题；预先选定版本仍未达到85%。这两个事实应同时报告。后续研究主线可依据训练OOF与验证共同支持，集中检查相对证据残差的稳定性、规则误报和单位/实体覆盖，不应继续无依据堆叠模型。','']

    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    summary=Path('EXPERIMENT_SUMMARY.md');old=summary.read_text(encoding='utf8');marker='## 第十轮追加：数学证据与受限融合'
    entry=f"{marker}\n\n41主配置、两套三折+全量、13组合及2单位控制，共56固定版本全部官方评分。预设规则选定{chosen}，验证{res[chosen]['validation']['correct']}/798，固定测试{res[chosen]['test']['correct']}/467={res[chosen]['test']['accuracy']:.4f}%；晋级={sel['promoted']}。测试只记录，不回流选型。\n\n最高固定测试记录为{top_test}：验证{res[top_test]['validation']['correct']}/798，测试{res[top_test]['test']['correct']}/467={res[top_test]['test']['accuracy']:.4f}%，超过85%；该记录不替代预先选择。相对证据残差在匹配消融中同时改善训练OOF和验证，组合并非一定进一步提升。\n\n对照、错题覆盖和资源见[runs/evidence_round/REPORT.md](runs/evidence_round/REPORT.md)，命令见[EVIDENCE_EXPERIMENTS.md](EVIDENCE_EXPERIMENTS.md)。\n"
    if marker in old:
        start=old.index(marker);end=old.find('\n## ',start+len(marker))
        summary.write_text(old[:start]+entry+(old[end:] if end>=0 else ''),encoding='utf8')
    else:summary.write_text(old+'\n\n'+entry,encoding='utf8')
    save(out/'report-integrity.json',{'all_variants_reported':len(res),'passed_checks':len(checks['variants']),
      'report_sha256':hashlib.sha256((out/'REPORT.md').read_bytes()).hexdigest()})
    print(json.dumps({'selected':chosen,'result':res[chosen],'highest_test_record':top_test,'module_representatives':module_best},ensure_ascii=False,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('runs/evidence_round'));main(p.parse_args().output)
