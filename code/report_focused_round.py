"""Generate matched contrasts and a complete Chinese focused-round report."""
import json,hashlib
from pathlib import Path
import numpy as np
from run_focused_round import SPECS,BASE,SEEDS
from run_fusion_experiments import save
OUT=Path('runs/focused_round')
def read(n):return json.loads((OUT/n).read_text())
def main():
    f=read('freeze.json');cmp=read('comparison.json');off=read('official-results.json');comp=read('compliance.json')
    records=cmp['records'];selected=f['selected'];checks=read('checks.json')
    assert len(records)==len(off)==len(f['variants'])==len(checks['variants'])
    for n,h in f['source_sha256'].items():assert hashlib.sha256(Path(n).read_bytes()).hexdigest()==h,n
    full=read('full-results.json');cv=read('cv-results.json')
    oof={s:dict(np.load(OUT/f'oof-{s}.npz')) for s in SEEDS};sc={s:dict(np.load(OUT/f'scales-{s}.npz')) for s in SEEDS}
    z=dict(np.load(OUT/'training-cache.npz'));y=z['y'];valid=z['valid'];votes=z['votes']
    def correct(n,s):
        vals=oof[s][n]/sc[s][n][z['fold_'+str(s)],None]+.25*(votes-1)
        vals[~valid]=-1e30;return y[np.arange(len(y)),vals.argmax(axis=1)].astype(bool)
    contrasts={}
    pairs=[]
    for features in ('base','full'):
        root=f'{features}_all_linear_l210'
        for style in ('narrow','broad'):
            pairs.append((f'style_{features}_{style}',root,f'{features}_{style}_linear_l210'))
    for style in ('all','broad'):
        for l2 in ('10','20'):
            root=f'full_{style}_linear_l2{l2}'
            for basis in ('hinges','interactions','both','orth_hinges','orth_both'):pairs.append((f'basis_{style}_{l2}_{basis}',root,f'full_{style}_{basis}_l2{l2}'))
    for features,style in [('base','all'),('full','broad')]:
        root=f'{features}_{style}_linear_l210'
        for policy in ('informative_full','informative_mean','hard_full','hard_mean','hard_mask_full','all_mask_full','hard_prep_mean'):
            pairs.append((f'supervision_{features}_{policy}',root,f'{features}_{style}_{policy}'))
    for label,a,b in pairs:
        delta=[int(correct(b,s).sum()-correct(a,s).sum()) for s in SEEDS]
        contrasts[label]={'control':a,'changed':b,'oof_gains_by_seed':delta,'mean_oof_gain':float(np.mean(delta)),
          'validation_gain':off[b]['validation']['correct']-off[a]['validation']['correct'],
          'test_gain_descriptive':off[b]['test']['correct']-off[a]['test']['correct']}
    save(OUT/'matched-contrasts.json',contrasts)
    # Numerical solutions to mathematically equivalent objectives need not be bit-identical.
    equivalence={}
    for features,style in [('base','all'),('full','broad')]:
        for a,b in [(f'{features}_{style}_linear_l210',f'{features}_{style}_informative_full'),
                    (f'{features}_{style}_all_mask_full',f'{features}_{style}_hard_mask_full')]:
            wa=np.load(OUT/'full'/a/'model.npz')['weight'];wb=np.load(OUT/'full'/b/'model.npz')['weight']
            equivalence[a+'__'+b]={'max_weight_difference':float(abs(wa-wb).max()),
              'objective_difference':abs(full[a]['final_objective']-full[b]['final_objective']),
              'validation_correct_difference':off[b]['validation']['correct']-off[a]['validation']['correct'],
              'test_correct_difference':off[b]['test']['correct']-off[a]['test']['correct']}
    save(OUT/'numerical-equivalence.json',equivalence)
    basis_audit={}
    for n,c in SPECS.items():
        if not c['basis'].startswith('orth_'):continue
        a=dict(np.load(OUT/'full'/n/'model.npz'))
        binary=np.array([len(np.unique(z['raw'][:,:,1024+j]))<=2 for j in range(50)])
        surviving=int(binary[a['orth_indices']].sum());assert surviving==0
        basis_audit[n]={'original_quantile_hinge_columns':4*len(a['scalar_keep']),'remaining_source_nonlinear_columns':len(a['orth_indices']),'binary_source_hinge_columns_remaining':surviving}
    save(OUT/'hinge-basis-audit.json',basis_audit)
    best_oof=max(SPECS,key=lambda n:records[n]['mean_oof_correct']);best_test=max(off,key=lambda n:off[n]['test']['correct'])
    e=off[selected];base=off[BASE];native=off['baseline_native_vote']
    lines=['# 严格对照优化实验报告','',
      f'本轮围绕三个优先方向，完成{len(SPECS)}个主配置、两套新三折划分（种子101/307，共{len(SPECS)*6}次折内拟合）、{len(SPECS)}次全量训练重训、11个组合、2个投票单位对照，共{len(off)}个冻结部署变体。',
      f'预先规则选定 **{selected}**：验证{e["validation"]["correct"]}/798，固定测试{e["test"]["correct"]}/467={e["test"]["accuracy"]:.4f}%。',
      f'本轮匹配的归一化基线：验证{base["validation"]["correct"]}/798，测试{base["test"]["correct"]}/467={base["test"]["accuracy"]:.4f}%；原始单位投票基线：验证{native["validation"]["correct"]}/798，测试{native["test"]["correct"]}/467={native["test"]["accuracy"]:.4f}%。',
      f'所有冻结版本最高测试记录为{off[best_test]["test"]["correct"]}/467={off[best_test]["test"]["accuracy"]:.4f}%；此项只描述，不用于回头选模。',
      '',
      '## 实验控制与边界','',
      '- 所有拟合只用课程训练数据。验证只在完整训练集重训后使用。全部模型、组合、选择和哈希固定后才开始测试评分。旧轮次资产和脚本保持不变。',
      '- 两套三折评估复用了同一4755题，不是9510道独立题。OOF是开发选择数据，不宣称完整嵌套、无偏的家族选择估计；已有验证集也有多轮使用历史。',
      '- 所有配置均使用float64全批量L-BFGS，最多100迭代/140函数评估；初始零权重，L2仅按显式对照变化。多正例组内目标不一定全局凸，不能保证全局最优。',
      '- 所有主配置和组合的分数均除以相应拟合训练题的题内中心化标准差，再固定加0.25票数奖励。归一化基线是匹配参照，原始单位基线单独记录，消除先前缺少投票单位对照的问题。',
      '- 预先晋级要求：两套OOF平均至少净增8题、每套非负、6折至少4折净增、最差折不低于-6题，验证不低于匹配基线。合格者优先按平均OOF、最差种子、验证、较少参数排名；否则保留基线。',
      '- 这些是工程筛选门槛，不是显著性检验。bootstrap按题重采样、合并同题两次正确性的平均差，区间为未校正多重搜索的探索结果。',
      '- 基础特征是1024维向量+22项原文本；完整特征是向量+50项标量。窄格式块移除9项，宽块移除13项；宽块还包含数字与运算符计数，不能都称作纯格式。',
      '- 加性模型均包含同样保留的线性项，之后分别加训练分位点hinge、6个指定交互或两者。派生特征也用训练统计标准化。本轮不是前轮未标准化GAM的直接复刻。',
      '- 首批训练后、测试前追加8个orth_hinges/orth_both对照：在每个源标量上合并重复结点，减去hinge对该源标量的仿射拟合，删除残差近零的列，再标准化。此举排除二值hinge仅重复线性项的情况；不宣称对所有其他变量全局正交。追加原因与已见数据记录在plan-amendment.json，原计划保留。',
      '',
      '## 损失分母负对照','',
      '全训练题4755；非全对题2513；至少两个可解析答案的分歧题2114。除明确的hard_prep_mean外，预处理都共享对应训练折的所有输入，以隔离损失变化。',
      '解析损失和梯度检查确认：保持原分母时，删去全对题完全不改变目标；屏蔽不可解析候选后，只保留分歧题并保持分母也完全等价。若改成仅对保留题取均值，就改变了数据项相对L2的强度。',
      '理论等价不要求有限预算优化结果逐比特相同；解析检查见objective-controls.json，数值解差异见numerical-equivalence.json。',
      '',
      f'## {len(SPECS)}个主配置：统一归一化单位＋0.25投票','',
      '| 配置 | 两套OOF正确/4755 | 相对基线净增 | 验证/798 | 固定测试/467 | 测试acc | 晋级 |',
      '|---|---|---|---:|---:|---:|---|']
    for n,c in SPECS.items():
        r=records[n];v=off[n]
        lines.append(f'| {n} | {list(r["oof_correct_by_seed"].values())} | {r["seed_gains"]} | {v["validation"]["correct"]} | {v["test"]["correct"]} | {v["test"]["accuracy"]:.2f}% | {"是" if r["eligible"] else "否"} |')
    lines+=['','## 匹配消融：改变相对控制的净变化','','| 对照项 | 控制 | 改变 | OOF两套净增 | 验证净增 | 固定测试净变化 |','|---|---|---|---|---:|---:|']
    for label,r in contrasts.items():
        lines.append(f'| {label} | {r["control"]} | {r["changed"]} | {r["oof_gains_by_seed"]} | {r["validation_gain"]:+d} | {r["test_gain_descriptive"]:+d} |')
    lines+=['','## 11个组合与单位控制','',
      f'代表成员只按训练OOF选出：{cmp["representatives"]}。测试不参与选择。','',
      '| 名称 | 组成 | 两套OOF净增 | 六折净增 | 验证/798 | 测试/467 | 晋级 |','|---|---|---|---|---:|---:|---|']
    for n,r in records.items():
        if n in SPECS:continue
        d=r['definition'];lines.append(f'| {n} | {list(zip(d["members"],d["weights"]))} | {r["seed_gains"]} | {r["fold_gains"]} | {off[n]["validation"]["correct"]} | {off[n]["test"]["correct"]} | {"是" if r["eligible"] else "否"} |')
    lines+=['','## 去重与去线性成分的分段特征审计','',
      '| 配置 | 原始分位点列 | 保留非线性列 | 其中二值源列 |','|---|---:|---:|---:|']
    for n,a in basis_audit.items():lines.append(f'| {n} | {a["original_quantile_hinge_columns"]} | {a["remaining_source_nonlinear_columns"]} | {a["binary_source_hinge_columns_remaining"]} |')
    lines+=['',
      '## 选定模型的证据与分歧题','',
      '选定模型的完整比较记录：','', '~~~json',json.dumps(records[selected],ensure_ascii=False,indent=2),'~~~','',
      '| 子集 | 题数 | 匹配基线正确 | 选定模型正确 |','|---|---:|---:|---:|']
    for group,r in cmp['validation_strata'].items():lines.append(f'| {group} | {r["n"]} | {r["methods"][BASE]} | {r["methods"][selected]} |')
    lines+=['',
      '只有一种可解析答案的题，在屏蔽无效候选后必选中正确数值。因此只改为报告分歧题准确率，不会改变这些方法的全体验证排名；它改善解释而不是凭空提升模型。',
      '',
      '## 本轮主要结论','',
      f'- 本轮训练内平均OOF最高主配置是{best_oof}；与匹配基线相比，两套净变化{records[best_oof]["seed_gains"]}。验证{off[best_oof]["validation"]["correct"]}题；测试仅作冻结版本记录。',
      f'- 按规则选定版本的固定测试较归一化基线净变化{e["test"]["correct"]-base["test"]["correct"]:+d}题，较原始单位基线{e["test"]["correct"]-native["test"]["correct"]:+d}题。',
      '- 本轮没有新配置通过全部晋级门槛，因此保留匹配基线；最高固定测试记录390/467，没有超过历史391/467，也未达到85%。门槛是事先设定的保守规则，本轮结果不能证明门槛本身最优。',
      '- 去格式的独立贡献较弱：完整特征移除窄块相对同特征基线的两套OOF净变化为[-5,+7]，移除宽块为[-2,+1]。不能把此前相对基础模型的提升全部归因于去格式，也不能断言格式一概有害。',
      '- 完整特征＋宽格式移除＋仅分歧题损失（保留原分母）相对基础匹配基线两套OOF净增[7,6]，验证747题持平；相对同特征的全部题训练仅净增[2,5]。这是小幅候选信号，未达到平均8题门槛，不因测试390题事后晋级。',
      '- 基础特征仅改为分歧题训练，OOF反而为[-1,-1]。监督组织的效果依赖特征表示，不能将只训练难题当作通用提升。',
      '- 非线性并未给出可靠改进：加性组合的OOF领先未迁移到验证；去掉仿射/重复列后，完整标量分段列由200降至64，宽去格式由148降至30，保留列中没有二值源。收益可能部分涉及重参数化/正则化，不能据此声称数学推理能力增强。',
      '- 删除全对题并对保留题取均值，等价于在原全题数据项下把L2从0.01降到0.01*(2513/4755)≈0.005285（折内比例相应变化）；其变化不是新监督信息。固定分母版本数值权重最大差约6.2e-12，验证与测试计数均相同。',
      '- 11个组合没有获得足够训练内与验证联合证据。后续更值得引入题目条件/目标量对齐及候选差异信息，而非继续扩大轮数或权重网格。',
      '- 逐项对照应同时检查两套OOF和外部验证；测试行不可用于重新选择正则化、训练题型、特征或融合权重。',
      '- 本轮每个方法只是有限预算验证，不能将未获提升等同于整个方法家族无效。旧版最高测试391/467是历史固定版本记录，不是本轮选择目标。',
      '',
      '## 成本、合规与复现','',
      f'- 首批与追加训练墙钟合计{read("stage-train-timing.json")["wall_seconds"]+(read("stage-train-initial-timing.json")["wall_seconds"] if (OUT/"stage-train-initial-timing.json").exists() else 0):.1f}秒，记录的{len(SPECS)*7}次主拟合合计{sum(r["seconds"] for r in cv)+sum(r["seconds"] for r in full.values()):.1f}秒。',
      f'- 硬件：{comp["hardware"].get("cpu",comp["hardware"]["platform"])}；四线程CPU训练与推理。最大单部署资产{comp["max_asset_bytes"]}字节，最大完整测试预测＋独立评分{comp["max_local_test_seconds"]:.3f}秒。',
      f'- {len(checks["variants"])}个部署变体通过NumPy推理、空/单/七题输入、任意ID、候选重排分数等变性、不可解析回退检查；全部本机限额通过：{comp["all_local_limits_pass"]}。',
      '- 官方数据、解析器、评分器未修改，无外部数据、预训练权重、新LLM生成或API。参考Xeon未实测，不能宣称官方CPU资格已认证。',
      '- 推理资产没有训练ID、标签或预测缓存。实验目录含训练记录，不是一个部署包；提交时只提供对应的完整model_bundle。',
      '- 命令、方法定义和AI辅助披露见[FOCUSED_EXPERIMENTS.md](../../FOCUSED_EXPERIMENTS.md)。AI实质参与代码、实验编排和分析。',
      '',
      '## 完整资源表','','| 方法 | 测试acc | 完整测试秒 | 资产字节 |','|---|---:|---:|---:|']
    for n,v in off.items():lines.append(f'| {n} | {v["test"]["accuracy"]:.4f}% | {v["test"]["fresh_prediction_plus_scoring_seconds"]:.3f} | {v["asset_bytes"]} |')
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    summary=Path('EXPERIMENT_SUMMARY.md');text=summary.read_text(encoding='utf8');marker='## 第九轮追加：分歧监督与匹配消融'
    if marker not in text:
        summary.write_text(text+f'\n\n{marker}\n\n{len(SPECS)}主配置、两套三折划分、{len(SPECS)*7}次折内/全量拟合、11组合和2单位控制。按预设门槛选定{selected}，验证{e["validation"]["correct"]}/798，固定测试{e["test"]["correct"]}/467={e["test"]["accuracy"]:.4f}%。测试不用于改选。\n\n完整对照和结论见[runs/focused_round/REPORT.md](runs/focused_round/REPORT.md)，复现命令见[FOCUSED_EXPERIMENTS.md](FOCUSED_EXPERIMENTS.md)。\n',encoding='utf8')
    save(OUT/'reproduction-manifest.json',{'freeze_sha256':hashlib.sha256((OUT/'freeze.json').read_bytes()).hexdigest(),
      'all_frozen_sources_unchanged':True,'all_variants_scored_and_checked':True,
      'report_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'report_sha256':hashlib.sha256((OUT/'REPORT.md').read_bytes()).hexdigest()})
    print(json.dumps({'selected':selected,'selected_result':off[selected],'best_test_record_descriptive':best_test,'report':str(OUT/'REPORT.md')},ensure_ascii=False))
if __name__=='__main__':main()
