"""Generate this round's report and a unified history of completed experiments."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np


def read(path): return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('runs/remaining_directions'))
    args=parser.parse_args();out=args.output
    f=read(out/'freeze.json');r=read(out/'experiment-results.json');t=read(out/'training-results.json')
    with (out/'validation-search.csv').open('w',newline='',encoding='utf-8-sig') as file:
        w=csv.writer(file);w.writerow(['family','hidden','regularization','lr','seed','epoch','valid_only_correct','weighted_correct','group_loss'])
        for a in t['checkpoints']:
            w.writerow([a['family'],a['config']['hidden'],a['config']['regularization'],a['config']['lr'],a['seed'],a['epoch'],a['validation_correct']['valid_only'],a['validation_correct']['weighted'],a['validation_group_loss']])
    with (out/'training-curves.csv').open('w',newline='',encoding='utf-8-sig') as file:
        w=csv.writer(file);w.writerow(['family','config','seed','epoch','training_objective_epoch_mean'])
        for a in t['curves']:w.writerow([a['family'],json.dumps(a['config']),a['seed'],a['epoch'],a['training_objective_epoch_mean']])
    lines=['# 第五轮：MLP、候选比较、文本与计算特征', '',
        '## 实验问题与设计', '',
        '完成三个此前未充分评估的方向：独立非线性评分器、利用候选集合及同答案组的上下文评分器、文本/算式信息。另设置联合上下文+文本算式模型，检验组合是否互补。所有模型只在训练集拟合，标准化统计量也只由训练集产生。', '',
        '- linear_control：无额外特征的线性组内模型，作为本轮匹配控制。',
        '- linear_text / linear_calc / linear_textcalc：分别在原始向量外加入22维文本/数字/格式特征、8维算式特征、全部30维特征，从头联合训练线性组内模型，不使用训练内模型预测训练融合器。',
        '- mlp：候选独立共享的一层ReLU网络，神经元32或64。',
        '- context：共享候选编码后拼接自身编码、整组均值、自身减整组均值、同答案组均值、自身减同答案组均值、答案票数比例，再通过非线性网络评分。无位置编码，候选重排时评分随候选重排。',
        '- context_textcalc：上下文模型的输入同时包含文本与算式特征。', '',
        '文本特征包括长度、格式、题目词汇/数字覆盖率、答案数值性质等，不等同于理解推理。算式特征用白名单AST检查有限的显式数值等式；支持简单分数/小数和四则运算，容许1e-3相对误差。无法识别的表达式是未知，不判错；不能用它证明整份推理有效。', '',
        '所有推理策略先屏蔽官方不能解析的候选。每个家族按独立评分的验证正确数选择一个模型，相同则比较组内损失；再对同一模型比较alpha=0和固定alpha=0.25。票数系数没有为新模型重新调节。测试在所有家族配置与哈希固定后才评分。', '',
        '## 训练与选择', '',
        '线性模型：全批量Adam、显式L2、学习率0.03，检查120/360/720轮；控制组L2固定0.001，其他线性模型比较0.001/0.01。神经网络：AdamW、Dropout=0.1、每批256题、学习率0.001，预设两个组合配置（32隐藏单元/0.001权重衰减，64隐藏单元/0.01权重衰减），检查20/40/80轮。不同容量与正则化一起改变，不能将二者贡献完全拆开。', '',
        '主实验种子2026。每个神经网络家族的选定配置额外用2027复核一次，只诊断稳定性，不事后换种子、不加入集成。不同训练方法的训练损失数值不能直接横向比较。', '',
        '| 家族 | 架构 | 特征 | 选定配置 | 轮次 | 独立验证正确 | 固定融合验证正确 |','|---|---|---|---|---:|---:|---:|']
    for family,a in f['selected'].items():
        lines.append(f"| {family} | {a['architecture']} | {a['features']} | {a['config']} | {a['epoch']} | {a['validation_correct']['valid_only']} | {a['validation_correct']['weighted']} |")
    lines += ['', '### 第二种子诊断', '', '| 家族 | 主种子独立/融合 | 复核种子独立/融合 |','|---|---:|---:|']
    for family,a in t['replications'].items():
        first=f['selected'][family]['validation_correct'];second=a['validation_correct']
        lines.append(f"| {family} | {first['valid_only']}/{first['weighted']} | {second['valid_only']}/{second['weighted']} |")
    lines += ['',f"总搜索及复核内部耗时{t['search_and_replication_seconds_excluding_startup_imports']:.3f}秒；主搜索记录{len(t['checkpoints'])}个预定检查点。CPU四线程，无GPU或新依赖。内部时间含数据/特征准备、训练、验证和导出，不含解释器启动与导入。", '',
        '## 官方评测与资源', '', '| 方法 | 验证集 | 测试集 | 资产KiB | 测试完整CPU耗时 |','|---|---:|---:|---:|---:|']
    for n,v in r['evaluations']['validation'].items():
        test=r['evaluations']['test'][n];size=r['asset_bytes'].get(n)
        size_text=f'{size/1024:.2f}' if size is not None else '上轮资产'
        lines.append(f"| {n} | {v['correct']}/798（{v['accuracy']:.4f}%） | {test['correct']}/467（{test['accuracy']:.4f}%） | {size_text} | {test['fresh_prediction_plus_scoring_seconds']:.3f}秒 |")
    lines += ['',f"本轮按验证结果推荐：{r['validation_recommendation']}。同分优先保留顺序较前的简单或已有模型。测试结果不参与本轮推荐。", '',
        '计时包括新预测进程和独立官方评分进程的启动、导入、加载、特征提取和预测，每项一次；微小差异不能视为稳定速度差。尚未在参考Xeon上验证。资产按每个互斥模型分别统计，不包括诊断种子文件；这些文件不在推理路径中。', '',
        '## 错误变化与分组', '', '| 方法 | 对上轮融合修正 | 破坏 | 对MLP独立修正 | 破坏 |','|---|---:|---:|---:|---:|']
    for n,a in r['validation_groups']['all']['methods'].items():
        p=a['vs_previous_weighted'];q=a['vs_mlp_valid_only']
        lines.append(f"| {n} | {p['fixed']} | {p['broken']} | {q['fixed']} | {q['broken']} |")
    lines += ['', '| 方法 | 分歧题正确/355 | 平票正确/88 | 唯一最高票正确/710 |','|---|---:|---:|---:|']
    for n in r['evaluations']['validation']:
        values=[r['validation_groups'][g]['methods'][n]['correct'] for g in ('answer_disagreement','tied_leaders','unique_leader')]
        lines.append('| '+n+' | '+' | '.join(map(str,values))+' |')
    lines += ['', '## 算式覆盖与特征解释', '',json.dumps(r['arithmetic_coverage'],ensure_ascii=False,indent=2), '',
        '以下为线性模型中标准化后绝对系数最大的额外特征，仅描述关联，不证明因果或推理能力。', '']
    for family in ('linear_text','linear_calc','linear_textcalc'):
        bundle=out/(family+'_valid_only')/'model_bundle';config=read(bundle/'config.json')
        with np.load(bundle/'model.npz',allow_pickle=False) as asset: weights=asset['linear_weight'].reshape(-1)[1024:]
        order=np.argsort(np.abs(weights))[::-1][:6]
        lines.append('- '+family+'：'+'；'.join(f"{config['feature_names'][i]}={weights[i]:+.4f}" for i in order))
    lines += ['', '## 不同答案分差的可靠性诊断', '',
        '只分析355道答案分歧题，分差按不同答案组最高分计算；各模型独立分四组。不是校准概率，同一开发验证集上的结果不能当独立泛化证明。', '',
        '| 方法 | 最低分差组 | 第二组 | 第三组 | 最高分差组 |','|---|---:|---:|---:|---:|']
    for n,quartiles in r['confidence_quartiles'].items():lines.append('| '+n+' | '+' | '.join(f"{q['accuracy']:.2f}%" for q in quartiles)+' |')
    lines += ['', '## 解释边界', '',
        '- context相对mlp同时增加集合结构、同答案关系、票数输入和网络参数；收益不能全部归因于某一个组件，需后续更细消融。',
        '- 文本表面特征不等于语义推理；算式正确也不等于建模正确，算式检查还可能因表达式抽取而出现噪声。',
        '- 单一验证划分、有限种子和持续开发选择会造成不确定性；本轮保留失败家族，不据测试成绩回头改模型。',
        '- 一部分同题所有候选都正确，组内目标对它们没有区分梯度；本轮保持目标不变，未额外引入联合BCE。',
        '- 本轮不引入外部数据或预训练参数，不通过ID查答案，不缓存新bank预测，推理离线且仅用输入材料。', '',
        '完整训练曲线、搜索、逐题变化和哈希位于本目录。总历史分析见code/EXPERIMENT_SUMMARY.md，复现见REMAINING_EXPERIMENTS.md。', '',
        'AI辅助披露：脚本、实验和报告由Codex辅助完成；最终作者需要理解、核查并披露实质性帮助。']
    lines += ['', '## 本轮结果分析', '',
        '独立MLP的验证独立正确数731，低于线性控制733；第二种子为724。当前配置未支持用MLP替换线性模型。上下文模型729也未超过MLP，测试下降且种子复核没有提供稳定优势；这只能否定本轮实现和搜索范围，不代表所有候选比较方法无效。', '',
        '线性文本特征独立评分743，较线性控制净增10题；固定融合746，较旧融合净增12题（修正22、破坏10）。收益同时覆盖平票组（65→70）和唯一最高票组（669→676）。答案分歧子集291→303，即81.97%→85.35%。', '',
        '线性算式特征独立评分735，固定融合741，提供较小收益；但文本+算式全部合并只有742，低于仅文本746。特征更多不保证效果更好，抽取噪声、特征关联和正则化均可能影响结果，本轮未进一步区分原因。', '',
        '文本最强系数包含答案是否整数、题目数字覆盖、新数字比例等，提示模型利用了数据分布与表达线索；不能据此宣称学会数学推理。has_valid_answer在屏蔽后的可选候选间取值相同，不能直接解释为其在这些候选中决定了选择，它还可能影响训练期间其他权重。', '',
        'context_textcalc相对纯context改善，但未超过线性文本方法，第二种子独立正确从737降到726，显示当前神经联合模型存在不稳定性。', '',
        '当前保留简单线性文本融合方法，完整测试正确387/467；它仍未达到85%。上述具体结论对应本次固定记录，若重跑出现数值差异应以新记录核查，不根据测试成绩调整模型。']

    (out/'REPORT.md').write_text(chr(10).join(lines)+chr(10),encoding='utf-8')
    history=[]
    def add(stage,name,v,test):history.append({'stage':stage,'name':name,'validation_correct':v['correct'],'validation_accuracy':v['accuracy'],'test_correct':test['correct'],'test_accuracy':test['accuracy']})
    initial=read(Path('runs/vector_logistic/experiment-results.json'))['evaluations']
    add('基线','多数投票',initial['baseline_validation'],initial['baseline_test'])
    add('独立向量','线性BCE，无屏蔽',initial['vector_validation'],initial['vector_test'])
    fusion=read(Path('runs/vector_vote_fusion/experiment-results.json'))['evaluations']
    for n in ('valid_only','vote_first','weighted'):add('投票融合',n,fusion['validation'][n],fusion['test'][n])
    objective=read(Path('runs/vector_objectives/experiment-results.json'))['evaluations']
    for n in ('group_valid_only','group_weighted'):add('目标对齐',n,objective['validation'][n],objective['test'][n])
    long=read(Path('runs/group_long_training/experiment-results.json'))['evaluations']
    for n in ('long_valid_only','long_weighted'):add('充分训练',n,long['validation'][n],long['test'][n])
    for n in f['variants']:add('本轮三方向',n,r['evaluations']['validation'][n],r['evaluations']['test'][n])
    summary=['# 已完成实验的统一分析', '',
        '数据划分固定：4755训练、798验证、467测试。训练拟合只使用训练集，参数与模型选择依据验证集；每轮固定配置后记录测试表现。以下将已评测的固定方法统一比较，测试表不是测试驱动的选型表。', '',
        '| 阶段 | 方法 | 验证正确/798 | 验证准确率 | 测试正确/467 | 测试准确率 |','|---|---|---:|---:|---:|---:|']
    for a in history:summary.append(f"| {a['stage']} | {a['name']} | {a['validation_correct']} | {a['validation_accuracy']:.2f}% | {a['test_correct']} | {a['test_accuracy']:.2f}% |")
    summary += ['', '## 已获得的结论', '',
        '1. 多数投票是强参照，但其86.22%的验证成绩包含443道仅一种可解析答案的容易题；在355道分歧题上只有69.01%。',
        '2. 固定向量包含投票之外的信号。BCE向量评分改善分歧题和平票题，但会破坏部分投票原本选对的题，说明证据互补。',
        '3. 官方解析有效性屏蔽消除必然不得分的选择；它是协议改进，不是更强的数学理解。',
        '4. 最高票作为强制规则不理想；小权重奖励比投票优先更好。',
        '5. 支持多个正确候选的组内选择目标优于已比较的BCE线性模型，表明训练目标对齐有实际价值。',
        '6. 延长线性训练并衰减学习率使部分轨迹优化趋稳，但按预设规则选定的模型没有获得额外准确率；保留旧模型。', '',
        '## 本轮三个方向应如何判断', '',
        'MLP主要比较mlp与linear_control；候选比较主要比较context与mlp；文本/计算先比较linear_text、linear_calc、linear_textcalc与linear_control，再比较context_textcalc与context。后两组存在架构容量或交互变化，不能视为完全单变量的因果证明。', '',
        '| 家族（独立屏蔽） | 验证正确数 | 相对线性控制净变化 | 测试记录 |','|---|---:|---:|---:|']
    control=r['evaluations']['validation']['linear_control_valid_only']['correct']
    for family in f['selected']:
        n=family+'_valid_only';v=r['evaluations']['validation'][n];test=r['evaluations']['test'][n]
        summary.append(f"| {family} | {v['correct']} | {v['correct']-control:+d} | {test['accuracy']:.2f}% |")
    summary += ['',f"当前按验证规则推荐：{r['validation_recommendation']}。对应资产路径见runs/remaining_directions/validation-recommendation.json。是否达到测试85%仅报告这个固定版本的实际结果，不据测试成绩选择其他家族。", '',
        '## 下一步与限制', '',
        '只有验证结果支持且错误互补时，才继续研究答案组评分、联合目标或小型集成。若收益小，应优先保留简单方法并做稳定性验证。最终报告需要选取清楚的研究主线、关键消融及失败案例，控制在10页以内，而不是逐项堆砌所有尝试。', '',
        '论文或排行榜成绩不能保证本项目达到85%。同一验证集持续开发也有选择偏差，后续若训练融合器，需使用按题目划分的训练集内部交叉验证预测。', '',
        '所有推理在四线程CPU上测量，必须以课程参考CPU资格为准；最终资产上限16MiB，完整预测加评分30秒。各轮REPORT.md记录本机硬件、时间、资产、种子、命令与局限。', '',
        '研究中的“正确”均指官方最终数值正确，不能当成每一步推理正确的标注。AI代码辅助、算法复用需在最终提交披露。']
    summary += ['', '## 本轮完成后的综合判断', '',
        '当前最有证据支持的组合是：固定候选向量＋线性组内选择目标＋解析有效性屏蔽＋少量文本/数字特征＋温和投票奖励。验证746/798=93.48%，测试387/467=82.87%。与初始多数投票相比，验证多对58题，测试多对64题。尚未达到85%；467题至少需要397题正确，当前还差净增10题。这只是目标差距统计，不据测试错题选择训练策略。', '',
        '| 方向 | 本项目目前证据 | 决策 |','|---|---|---|',
        '| 答案共识 | 票数有用，但错误也能获得共识 | 作为弱奖励，不做最高票硬约束 |',
        '| 独立向量 | 轻量线性模型已有明显信号 | 保留 |',
        '| 解析有效性 | 消除必然不得分的候选 | 保留 |',
        '| 组内目标 | 相对已试BCE改善任务选择表现 | 保留 |',
        '| 更长线性训练 | 优化趋稳但选定成绩不升 | 暂停增加轮次 |',
        '| 小型MLP | 当前搜索与复核未超过线性验证参照 | 不替换，记录失败 |',
        '| 集合候选比较 | 当前上下文网络未带来优势 | 不纳入当前部署 |',
        '| 文本/数字特征 | 本轮收益最清楚，且成本低 | 保留，同时承认表面分布线索 |',
        '| 有限算式检查 | 有辅助收益，但与文本合并不增益 | 暂不加入当前部署，保留研究结果 |',
        '| 置信度 | 不同答案组分差比候选分差更可解释 | 用于诊断，尚不视为校准概率 |', '',
        '神经网络的失败可能与样本量、优化、模型结构或正则化有关，本轮无法确定唯一原因。算式检查只覆盖验证候选的2057/3192≈64.44%，覆盖并不等于检查可靠度；未覆盖为未知，检测到不一致也不等于整份解答必错。', '',
        '后续若继续，优先做文本内部消融（数值性质、题目覆盖、格式长度分别贡献多少）与按题目划分的训练内交叉验证，再考虑答案组评分或基于互补错误的少量模型融合。不能因为某些模型整体较弱就直接断言没有集成价值，也不能在未验证互补性时堆叠全部模型。', '',
        '本轮13条主训练轨迹、3次选定神经配置的第二种子复核，39个主验证检查点，搜索与复核约165秒；均使用CPU四线程。当前推荐推理资产15404字节，完整测试预测+独立评分约0.766秒。本机i9-12900H，未在课程参考CPU上认证。所有官方文件保持原样，NumPy/Torch前向一致性、受限算式安全、可变题数、候选重排与未知ID检查通过。']

    Path('EXPERIMENT_SUMMARY.md').write_text(chr(10).join(summary)+chr(10),encoding='utf-8')
    save_path=out/'all-experiments.json';save_path.write_text(json.dumps(history,ensure_ascii=False,indent=2)+chr(10),encoding='utf-8')
    print(out/'REPORT.md');print('EXPERIMENT_SUMMARY.md')


if __name__=='__main__':main()
