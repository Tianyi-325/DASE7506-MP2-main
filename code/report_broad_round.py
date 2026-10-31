"""Generate the complete Chinese report from frozen experiment artifacts."""
import json,hashlib
from pathlib import Path
import numpy as np
from broad_training import SPECS
from run_broad_round import DIRECTIONS
OUT=Path('runs/broad_round')
def read(name):return json.loads((OUT/name).read_text())
def main():
    f=read('freeze.json');cmp=read('comparison-results.json');official=read('official-results.json')
    audit=read('data-audit.json');cv=read('cv-training-records.json');full=read('full-training-records.json')
    compliance=read('compliance.json');cal=read('calibration.json');checks=read('checks.json')
    chosen=f['selected'];record=cmp['records'];selected=official[chosen]
    labels={
      'baseline':'向量＋原22项文本基线','gbdt':'原生浅树提升 BCE','lambdamart':'Lambda 加权排序树',
      'gam':'加性分段线性＋指定交互','fm':'低秩FM修正','rff':'随机傅里叶特征',
      'charcnn':'从零训练字符CNN修正','supcon':'题内监督对比修正','extended_features':'扩展数值/语义/计算特征',
      'supervision_balanced':'按正确候选数平衡题目损失','valid_training_mask':'训练时排除不可解析候选',
      'stable_features':'训练内双半样本筛选特征','no_style':'去格式特征','numeric_quality':'替换旧算式检查的严格特征',
      'residual':'残差MLP16','residual_width32':'残差MLP32','residual_dropout':'残差＋dropout',
      'residual_adam_l2':'残差Adam显式L2','linear_lbfgs':'线性L-BFGS','linear_earlystop':'线性内部早停',
      'residual_batch128':'残差小批量128','residual_ema':'残差EMA','residual_swa':'残差SWA','residual_sam':'残差SAM'}
    lines=['# 本轮广泛优化实验报告','',
      f'本轮覆盖先前列出的21个方向：24个主配置，三折训练内评估、内部早停与全量训练集重训，以及{len(record)-2*len(SPECS)}个组合配置。主配置分别保留无投票/固定0.25投票，因此共有{len(record)}个冻结部署变体。',
      '每个方向为有界原型验证，不代表穷尽结构、超参数或论文官方实现。外部包下载失败，树/排序/加性模型采用本项目原生小型实现。',
      '',
      f'按预先规则选择 **{chosen}**：OOF {record[chosen]["oof_correct"]}/4755；验证{selected["validation"]["correct"]}/798={selected["validation"]["accuracy"]:.4f}%；固定后测试{selected["test"]["correct"]}/467={selected["test"]["accuracy"]:.4f}%。',
      '模型选择在所有测试评分之前写入freeze.json；下表测试仅为冻结版本的描述，不用于改选。',
      '',
      '## 协议与可信度','',
      '三折按题目划分，各1585题。每折神经网络和线性早停设置使用外层训练部分中的85/15内部划分选择轮次，再在完整外层训练部分重训。全量训练重训轮次为三折内部所选轮次的中位数。',
      '标准化、PCA、样条结点、监督特征筛选全部局限于相应拟合子集。训练输入不使用测试数据或测试参考答案。',
      '晋级门槛：相对本轮匹配基线，OOF至少净增5题，至少两折净增，最差折不低于-5题，外部验证再至少净增3题。合格者按OOF正确数优先、验证正确数打破平局；无人合格保留基线。',
      '这些门槛是本轮预先设定的工程规则，不是统计显著性证明。OOF用于开发选择，既有验证集曾多轮复用；不将任何一个称作完全无偏的最终泛化估计。配对bootstrap为探索性区间，未校正多重搜索。',
      '本轮将标准化特征截断到±20，和旧实现存在这一差别。本轮带投票基线复现746/798和387/467的计数；不带投票基线验证742题，与旧版743题有差异，故所有增益均相对本轮匹配基线。推理不依赖Torch。',
      '',
      '## 24个主配置（统一固定0.25投票）','',
      '| 方法 | OOF/4755 | 三折相对基线净增 | 验证/798 | 固定测试/467 | 测试acc | 通过晋级 |',
      '|---|---:|---|---:|---:|---:|---|']
    for name in SPECS:
        key=name+'_vote';r=record[key];e=official[key]
        lines.append(f'| {labels[name]} | {r["oof_correct"]} | {r["fold_gains"]} | {r["validation_correct"]} | {e["test"]["correct"]} | {e["test"]["accuracy"]:.2f}% | {"是" if r["promotion_eligible"] else "否"} |')
    lines+=['','## 21个方向的对应记录','','| 方向 | 本轮落实 | 结果入口 |','|---|---|---|']
    direction_names={'A1':'梯度提升树','A2':'树排序','A3':'加性模型与交互','A4':'低秩FM','A5':'显式核特征','A6':'小型文本CNN','A7':'监督对比学习','B1':'训练内评估协议','B2':'晋级标准与不确定性','B3':'有效监督组织','B4':'解析与数据审计','B5':'计算与题意特征','B6':'特征稳定性筛选','B7':'融合尺度与置信度校准','C1':'残差训练','C2':'容量和正则化','C3':'优化器与收敛','C4':'早停与轮次','C5':'批量大小','C6':'权重平均','C7':'SAM'}
    for key,methods in DIRECTIONS.items():
        entries=[]
        for n in methods:
            k=n+'_vote'
            if k in record:entries.append(f'{n}: OOF {record[k]["oof_correct"]}, 验证{record[k]["validation_correct"]}')
            else:entries.append(n)
        lines.append('| '+key+' '+direction_names[key]+' | '+', '.join(methods)+' | '+'; '.join(entries)+' |')
    lines+=['','## 合理组合：按训练OOF排序','','| 组合 | OOF/4755 | 三折净增 | 验证/798 | 固定测试/467 | 测试acc | 晋级 |','|---|---:|---|---:|---:|---:|---|']
    combos=[n for n in record if len(record[n]['definition']['members'])>1]
    for n in sorted(combos,key=lambda n:record[n]['oof_correct'],reverse=True):
        r=record[n];e=official[n]
        lines.append(f'| {n} | {r["oof_correct"]} | {r["fold_gains"]} | {r["validation_correct"]} | {e["test"]["correct"]} | {e["test"]["accuracy"]:.2f}% | {"是" if r["promotion_eligible"] else "否"} |')
    lines+=['','## 数据、特征与有效监督','',
      f'- 训练集全对题{audit["train"]["all_positive_zero_group_gradient_questions"]}/4755，组内目标下没有区分梯度；存在有效区分监督的题仅{4755-audit["train"]["all_positive_zero_group_gradient_questions"]}道。不能把候选行数当成独立训练题数。',
      '- 训练/验证规范化文本重复与跨划分精确重合均为0；这不能排除近似或语义重复。',
      f'- 验证算式检查覆盖：旧规则{audit["validation"]["old_equation_candidate_coverage"]}/3192，严格整行规则{audit["validation"]["strict_equation_candidate_coverage"]}/3192；严格规则发现{audit["validation"]["strict_detected_inconsistent_candidates"]}个候选存在不一致算式。严格不等于已证明更可靠；最终答案标注无法判定每一步推理。',
      '- 保留官方解析器和标签，合成算式包括正常四则运算、错误等式、除零、变量、单位后缀与代码字符串。未知不会当作算错。',
      '- 特征筛选用拟合子集内两个随机半样本的题内中心化相关系数，同号且绝对值均>0.015；无监督统计同样仅在拟合子集学习。逐折原文本权重见feature-stability.json。',
      '',
      '## 校准与训练过程','',
      '温度校准对不同数值答案组计算NLL，保持argmax不变，因此不宣称准确率提升。下列折为在基模型OOF预测上进行的第二层交叉拟合，不等同于完整嵌套评估。','',
      '| 折 | 温度 | 原NLL | 校准NLL |','|---|---:|---:|---:|']
    for r in cal['folds']:lines.append(f'| {r["fold"]} | {r["temperature"]} | {r["raw_nll"]:.4f} | {r["calibrated_nll"]:.4f} |')
    lines+=['','| 配置 | 各折最终训练轮次 | 全训练重训轮次 |','|---|---|---:|']
    for n in SPECS:lines.append(f'| {n} | {[r["epochs"] for r in cv if r["method"]==n]} | {full[n]["epochs"]} |')
    total_train=sum(r['seconds']+(r['inner']['seconds'] if r.get('inner') else 0) for r in cv)+sum(r['seconds'] for r in full.values())
    stage=read('stage-train-timing.json')
    lines+=['','## 验证分组与错题分析','',
      '详细逐题记录见validation-error-cases.json，子集统计见subgroup-analysis.json。该分析只使用验证标签。',
      '本轮选定组合在355道分歧题上由303题提升至306题；整体749/798包含443道仅一个可解析答案的容易题。',
      '相对基线修正6题，同时破坏3题。平票题净变化为0，收益主要来自非平票题；不能据此宣称解决了所有共识错误。',
      '训练OOF到全量重训的分数标准差审计见fusion-scale-audit.json；分数尺度接近也不能保证错误结构相同。','',
      '## 成本与限制','',
      f'- 训练阶段墙钟约{stage["wall_seconds"]:.1f}秒；主拟合和内部选轮记录合计约{total_train:.1f}秒，其余包含预处理、基线缓存、导出与评分等。可恢复缓存重跑时墙钟不能代表首次全部成本。',
      '- 本轮另做两次小样本数值检查；可选依赖安装失败日志保留在dependency-install.log。没有额外外部模型训练。',
      f'- CPU：{compliance["hardware"].get("cpu","见compliance.json")}，四线程；最大单个部署资产{compliance["max_asset_bytes"]}字节，最大完整本机测试预测＋独立评分{compliance["max_local_test_seconds"]:.3f}秒。',
      f'- 所有本机限额检查通过：{compliance["all_local_limits_pass"]}；官方原始文件校验通过；{len(checks["variants"])}个变体通过空输入、任意ID、候选重排与不可解析回退检查。',
      '- 未在参考Xeon上实测，因此不声称已取得官方资源资格。',
      '- 浅树只看32维PCA和人工特征，失败不能排除其他树模型；字符CNN只读固定256字符，失败不能排除完整文本架构。对比学习仅有同题多个正确候选且存在错误候选时提供局部正负对信号。',
      '- 加性模型同时改变特征形式与L2强度；组合同时改变成员与分数单位下的投票强度，缺少完整匹配消融，不能将收益唯一归因于非线性或融合。',
      '- 批量大小比较使用轮次上限和内部早停，未严格匹配梯度更新次数或计算量；只反映当前训练配置，不证明小批量本身有害。',
      '- 残差EMA/SWA共享内部早停，若早停轮数小于平均启动轮数，它们实际退化为原始检查点，应据轮次解释，不能宣称检验了充分权重平均。',
      '- 新模型和训练策略均为有界预算，不将未获提升解释为方法普遍无效。全部测试结果保持描述性，推荐不随后改变。',
      '',
      '## 本轮分析结论','',
      '1. 本轮没有超过既有391/467=83.73%的最高固定版本记录，也未达到85%。本轮按预先门槛选定组合383/467=82.01%，低于匹配基线387/467=82.87%。不据测试结果事后改选。',
      '2. 外部思路中，加性模型在三折分别净增6、7、5题，表现最稳定，但验证只增加2题，固定测试381题。它有训练内信号，尚无跨划分一致提升证据；不能以单次结果否定整个方法家族。',
      '3. 去格式版本OOF净增17题，相对扩展全特征版本也净增8题，验证与扩展版同为747题。其390题固定测试记录仅为描述；继续研究该方向的依据应是训练内稳定性，而非测试排名。',
      '4. 监督特征筛选OOF净增7题，但没有外部验证增益；严格算式减少覆盖，未带来可靠增益。提升特征精度不必然提高选择准确率。',
      '5. L-BFGS把完整训练目标从约0.172834降到0.172811，梯度范数从约0.00147降到0.000037，验证仍为746题。内部早停三折都选60轮，验证仍为746题，固定测试386题，较120轮基线少1题。训练过程更精确或更久，当前未转化为准确率收益。',
      '6. CNN、监督对比、残差网络、SAM与批量调整没有稳定超过基线；EMA/SWA在提前停止时可能尚未启动平均，因此不能将其当成充分权重平均的全面否定。',
      '7. 30个组合中，只有两个通过本轮工程晋级门槛。选中组合OOF净增10、验证净增3，但两处配对探索区间均含零；测试回落再次说明较弱筛选门槛不能保证泛化，不能继续只靠扫描融合权重。',
      '8. 温度在三折均选1.0，当前网格没有改善答案组NLL。置信度校准与提高argmax准确率是不同目标。',
      '9. 后续若继续，应先在训练内以答案分歧题为重点复核加性/去格式/监督筛选，增加匹配正则化与投票单位的消融；避免无边界加轮数或仅扩展融合网格。',
      '',
      '## 论文复用与AI披露','',
      '原生实现借鉴梯度提升、Lambda排序、加性模型、FM、RFF、TextCNN、监督对比学习、AdamW、SWA、SAM；论文链接、实现差异与准确复现命令见../../BROAD_EXPERIMENTS.md。大量实现、实验编排和分析由AI辅助，最终提交应保留披露。',
      '',
      '## 全部冻结变体（含无投票消融）','',
      '| 名称 | OOF | 验证 | 固定测试 | 时间秒 | 资产字节 |','|---|---:|---:|---:|---:|---:|']
    for n,r in record.items():
        e=official[n];lines.append(f'| {n} | {r["oof_correct"]} | {r["validation_correct"]} | {e["test"]["correct"]} | {e["test"]["fresh_prediction_plus_scoring_seconds"]:.3f} | {e["asset_bytes"]} |')
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    summary=Path('EXPERIMENT_SUMMARY.md');old=summary.read_text(encoding='utf8')
    marker='## 第八轮追加：三类21方向与组合'
    if marker not in old:
        text=f'\n\n{marker}\n\n本轮24主配置、{len(combos)}组合、{len(record)}个冻结变体。按训练内三折稳定性与验证晋级门槛选定{chosen}，验证{selected["validation"]["correct"]}/798，固定测试{selected["test"]["correct"]}/467={selected["test"]["accuracy"]:.4f}%。测试只作冻结版本记录，不用于改选。\n\n完整逐项结果、全部变体、协议边界和资源记录见[runs/broad_round/REPORT.md](runs/broad_round/REPORT.md)，命令与论文复用见[BROAD_EXPERIMENTS.md](BROAD_EXPERIMENTS.md)。\n'
        summary.write_text(old+text,encoding='utf8')
    assert len(f['variants'])==len(official)==len(checks['variants'])==len(record)
    for name,h in f['source_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
    sources=['broad_models.py','broad_training.py','run_broad_round.py','check_broad_round.py','report_broad_round.py','analyze_broad_round.py','reasoning_features.py','vector_vote_fusion.py','vector_logistic.py','common.py','train_vector.py','run_fusion_experiments.py','predict.py','score_predictions.py']
    provenance={'original_freeze_sha256':hashlib.sha256((OUT/'freeze.json').read_bytes()).hexdigest(),'all_frozen_variants_scored_and_checked':True,'selected':chosen,'source_sha256':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in sources},'note':'Supplementary complete source snapshot generated after evaluation; original pre-test freeze preserved.'}
    (OUT/'reproduction-manifest.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'report':str(OUT/'REPORT.md'),'selected':chosen,'result':selected},ensure_ascii=False))
if __name__=='__main__':main()
