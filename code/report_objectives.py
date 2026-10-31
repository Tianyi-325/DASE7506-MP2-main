"""Summarize frozen objective comparisons and training curves."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='4'
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from common import load_inputs
from run_fusion_experiments import labels,save
from vector_logistic import candidate_scores
from vector_vote_fusion import answer_information


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('runs/vector_objectives'))
    args=parser.parse_args()
    out=args.output
    freeze=json.loads((out/'freeze.json').read_text())
    training=json.loads((out/'training-results.json').read_text())
    results=json.loads((out/'experiment-results.json').read_text())
    records=training['grid_records']
    curves=training['training_curves']
    with (out/'training-curves.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(curves[0]))
        writer.writeheader()
        writer.writerows(curves)
    with (out/'validation-search.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f)
        writer.writerow(['objective','lr','l2','epoch','validation_loss','valid_only_correct','weighted_correct','gradient_norm'])
        for r in records:
            writer.writerow([r['objective'],r['lr'],r['l2'],r['epoch'],r['validation_loss'],r['validation_correct']['valid_only'],r['validation_correct']['weighted'],r['gradient_norm_before_step']])
    lines=['# 第三轮：训练充分性与多正例组内选择', '',
           '## 设计', '',
           '本轮保持1024维固定向量、线性评分器、训练集标准化不变。只用训练集拟合，验证集选择配置。两种目标分别从相同的2个学习率×3个L2×3个检查轮次中选择，共36个候选检查点；底层训练轨迹12条。检查点以外只记录训练损失，不参与验证选择。', '',
           '- BCE：每个候选最终数值正确为1，否则为0，候选级二元交叉熵。',
           '- Group：负对数“全部正确候选的softmax概率之和”，即 logsumexp(全部分数)−logsumexp(正确候选分数)。多个正确候选都能贡献正概率，不任意指定唯一正确答案。',
           '- 两者均允许多个正确候选；不同点是BCE分别拟合候选正确性，Group直接优化组内选到任意正确候选的概率。',
           '- Adam全批量CPU训练，L2惩罚权重不惩罚截距。Group的共同截距会抵消，固定为0。种子2026；零初始化且无随机批次，本轮不以多种子作为主要稳定性验证。',
           '- 每种目标只选择一个评分器，依据有效性屏蔽后的验证准确率，相同则依据各自的验证目标损失。然后对同一权重比较屏蔽策略与固定alpha=0.25融合；不为融合另选权重，也不重新搜索alpha。', '',
           '这不是完全等价的正则化比较：BCE和Group损失尺度不同，数值相同的L2不代表相同有效约束。固定alpha在不同目标的logit尺度下也不必具有相同意义。', '',
           '## 训练资源与监督结构', '',
           f"训练题数：{training['training_questions']}；四个候选全正确：{training['all_correct_train_questions']}；Group具有区分信号的题：{training['group_informative_train_questions']}。全正确题Group数据损失为0，而BCE仍使用它们。", '',
           f"训练/验证搜索内部耗时 {training['training_search_seconds_excluding_startup_imports']:.3f} 秒，不包含Python启动与导入。CPU四线程，无GPU、外部数据或额外预训练权重。", '',
           '## 验证选择的配置', '', '| 目标 | 学习率 | L2 | 轮次 | 屏蔽后正确 | 固定融合正确 | 验证目标损失 |','|---|---:|---:|---:|---:|---:|---:|']
    for objective,r in freeze['selected'].items():
        lines.append(f"| {objective} | {r['lr']} | {r['l2']} | {r['epoch']} | {r['validation_correct']['valid_only']} | {r['validation_correct']['weighted']} | {r['validation_loss']:.6f} |")
    lines += ['', '## 训练充分性检查', '',
              '下表仅取本轮BCE所选学习率/L2对应的同一训练轨迹，用于区分训练目标下降与验证选择准确率变化。梯度范数是相应epoch更新前的值。', '',
              '| 轮次 | 训练数据损失 | 训练含L2损失 | 梯度范数 | 验证目标损失 | 验证屏蔽正确 | 验证融合正确 |','|---|---:|---:|---:|---:|---:|---:|']
    selected=freeze['selected']['bce']
    for epoch in (120,360,1000):
        c=next(r for r in curves if r['objective']=='bce' and r['lr']==selected['lr'] and r['l2']==selected['l2'] and r['epoch']==epoch)
        v=next(r for r in records if r['objective']=='bce' and r['lr']==selected['lr'] and r['l2']==selected['l2'] and r['epoch']==epoch)
        lines.append(f"| {epoch} | {c['train_data_loss']:.6f} | {c['train_regularized_loss']:.6f} | {c['gradient_norm_before_step']:.6g} | {v['validation_loss']:.6f} | {v['validation_correct']['valid_only']} | {v['validation_correct']['weighted']} |")
    lines += ['', '不能仅因训练损失下降就认定选择效果更好，也不能仅因检查到1000轮就声称所有配置已严格收敛。完整轨迹见training-curves.csv，全部验证检查点见validation-search.csv。', '',
              '## 官方结果', '', '| 方法 | 验证集 | 测试集 | 验证完整耗时 | 测试完整耗时 |','|---|---:|---:|---:|---:|']
    for name,v in results['evaluations']['validation'].items():
        t=results['evaluations']['test'][name]
        lines.append(f"| {name} | {v['correct']}/{v['n']}（{v['accuracy']:.4f}%） | {t['correct']}/{t['n']}（{t['accuracy']:.4f}%） | {v['fresh_prediction_plus_scoring_seconds']:.3f}秒 | {t['fresh_prediction_plus_scoring_seconds']:.3f}秒 |")
    lines += ['', f"本轮按验证集推荐：{freeze['validation_preferred_variant']}。同分时按预先固定的变体顺序优先BCE和更简单选择策略。所有测试评分在freeze.json写出并校验后执行，不依据测试成绩调整配置或本轮推荐。", '',
              '## 验证错误变化', '', '| 新方法 | 对原屏蔽模型：修正/破坏 | 对原融合：修正/破坏 |','|---|---:|---:|']
    for name in freeze['variants']:
        r=results['validation_groups']['all']['methods'][name]
        a=r['vs_original_valid_only'];b=r['vs_original_weighted']
        lines.append(f"| {name} | {a['fixed']}/{a['broken']} | {b['fixed']}/{b['broken']} |")
    lines += ['', '| 验证分组 | 题数 | '+ ' | '.join(results['evaluations']['validation'])+' |', '|---|---:|'+ '|'.join(['---:']*len(results['evaluations']['validation']))+'|']
    for group,r in results['validation_groups'].items():
        lines.append(f"| {group} | {r['n']} | "+' | '.join(f"{v['correct']}（{v['accuracy']:.2f}%）" for v in r['methods'].values())+' |')
    bank,arrays=load_inputs('validation')
    y=labels(bank,'validation')
    answers,counts,votes=answer_information(bank)
    confidence={}
    lines += ['', '## 不同答案之间的分差与可靠性', '',
              '只分析至少两种可解析答案的355题，按答案组最高最终分数差分成四组。分差是描述性指标，不是校准概率；Group分数也不能直接经过sigmoid解释为候选正确概率。', '',
              '| 方法 | 最低分差组准确率 | 第二组 | 第三组 | 最高分差组 |','|---|---:|---:|---:|---:|']
    for name,v in freeze['variants'].items():
        scores=candidate_scores(bank,arrays,out/name/'model_bundle')
        if v['mode']=='weighted':
            scores+=0.25*(votes-1)
        data=[]
        for i,c in enumerate(counts):
            if len(c)<2:
                continue
            bests=sorted((max((scores[i,j],j) for j,a2 in enumerate(answers[i]) if a2==a) for a in c),reverse=True)
            # For tied final scores use the same earliest-candidate rule as inference.
            chosen=int(np.where(votes[i]>0,scores[i],-np.inf).argmax())
            data.append((float(bests[0][0]-bests[1][0]),bool(y[i,chosen])))
        data.sort(key=lambda item:item[0])
        quartiles=[]
        for indices in np.array_split(np.arange(len(data)),4):
            vals=[data[j] for j in indices]
            quartiles.append({'n':len(vals),'accuracy':100*sum(v[1] for v in vals)/len(vals),'min_margin':vals[0][0],'max_margin':vals[-1][0]})
        confidence[name]=quartiles
        lines.append('| '+name+' | '+' | '.join(f"{q['accuracy']:.2f}%" for q in quartiles)+' |')
    save(out/'validation-confidence.json',confidence)
    lines += ['', '## 资产与限制', '',f"本机：{results['hardware'].get('cpu_name','unknown')}，四线程。完整计时为一次新预测进程加独立官方评分进程，包含启动、导入、加载和解析；细小时间差不作稳定速度结论。尚未在参考Xeon上测量。", '',
              '| 变体 | 资产字节 | MiB |','|---|---:|---:|']
    for name,size in results['asset_bytes'].items():
        lines.append(f'| {name} | {size} | {size/2**20:.6f} |')
    lines += ['', '各变体互斥部署，不是四模型集成。推理只依赖NumPy，训练使用现有PyTorch。训练均为CPU。训练集拟合统计量已折叠进导出的线性权重，能直接处理新bank而不重训。', '',
              '本轮比较同时包含更长训练与新目标；判断目标收益应以本轮BCE为主要参照，而非只与上一轮较短训练比较。模型选择使用同一验证集，需警惕持续开发造成的乐观偏差。保留所有尝试，包括失败目标。', '',
              '复现方法见OBJECTIVE_EXPERIMENT.md。源码和资产哈希见freeze.json；逐题错误变化见validation-case-comparisons.json。', '',
              'AI辅助披露：本轮代码、运行及报告由Codex辅助完成，最终作者需理解、核查并披露实质性帮助。']
    lines += ['', '## 本轮可支持的结论', '',
              '1. 在预定搜索范围内，按独立评分选择的BCE配置仍为上一轮的lr=0.03、L2=0.01、120轮，没有发现仅延长训练就能超过它的独立评分器。',
              '2. lr=0.03长期训练出现优化波动，不能把其成绩下降全部归因为过拟合；lr=0.01、L2=0.01的训练正则化损失在360至1000轮基本稳定，仍未获得更高独立验证准确率。',
              '3. 相同线性模型下，Group独立评分从720提升到733题，支持训练目标与组内选择任务对齐具有价值；不同正则化尺度和有效监督量也是比较的限制。',
              '4. 固定融合在Group上仅增加1道验证正确题，因此不能把主要提升归功于投票；融合系数未为新logit尺度调整。',
              '5. 本轮选择评分器的指标是独立屏蔽后的验证准确率。其他BCE检查点的固定融合可能达到更高成绩（例如725题），并不改变预设选择规则；未根据次要指标事后改选。', '',
              '### 低学习率BCE的稳定性参照', '',
              '| 学习率 | L2 | 轮次 | 训练含L2损失 | 梯度范数 | 验证屏蔽正确 |','|---:|---:|---:|---:|---:|---:|']
    for epoch in (120,360,1000):
        c=next(r for r in curves if r['objective']=='bce' and r['lr']==0.01 and r['l2']==0.01 and r['epoch']==epoch)
        v=next(r for r in records if r['objective']=='bce' and r['lr']==0.01 and r['l2']==0.01 and r['epoch']==epoch)
        lines.append(f"| 0.01 | 0.01 | {epoch} | {c['train_regularized_loss']:.9f} | {c['gradient_norm_before_step']:.6g} | {v['validation_correct']['valid_only']} |")

    (out/'REPORT.md').write_text(chr(10).join(lines)+chr(10),encoding='utf-8')
    print(out/'REPORT.md')


if __name__=='__main__':
    main()
