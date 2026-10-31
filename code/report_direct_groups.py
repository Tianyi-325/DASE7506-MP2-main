"""Report direct group objectives, joint consensus, train-split stability and mixtures."""
import argparse
import csv
import json
from pathlib import Path


def read(p):return json.loads(p.read_text(encoding='utf-8'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('runs/direct_group_round'));args=p.parse_args();out=args.output
    f=read(out/'freeze.json');r=read(out/'experiment-results.json');t=read(out/'training-results.json');chosen=read(out/'validation-recommendation.json')
    with (out/'validation-search.csv').open('w',newline='',encoding='utf-8-sig') as file:
        w=csv.writer(file);w.writerow(['family','l2','epoch','mixture_weight','counts_by_alpha','validation_objective'])
        for a in t['records']:w.writerow([a['family'],a.get('l2'),a.get('epoch'),a.get('weight'),json.dumps(a['validation_correct']),a.get('validation_objective')])
    with (out/'training-curves.csv').open('w',newline='',encoding='utf-8-sig') as file:
        w=csv.DictWriter(file,fieldnames=list(t['curves'][0]));w.writeheader();w.writerows(t['curves'])
    lines=['# 第七轮：直接答案组训练与联合共识', '',
        '## 研究问题', '',
        '此前答案组模型学习的是冻结基础分数的元模型，本轮直接从1024维向量与22维文本特征学习候选分数，再在训练目标内部聚合同答案候选。保持原始数据、官方解析器和评分器不变。', '',
        '## 方法与差异', '',
        '- control：原候选级多正例组内损失，固定L2=0.01、120轮，作为原文本单模型重现。',
        '- group_mean：同答案候选分数平均，再对不同答案训练选择损失。',
        '- group_max：每个答案组取最高候选分数。',
        '- group_logmeanexp：logsumexp(组内候选分数)−log(组内候选数)，去除相同分数重复候选带来的额外概率质量。',
        '- joint_candidate：在原候选目标中联合学习票数、票数差、数值性质×支持度/分歧程度交互。',
        '- joint_group：使用相同联合特征，但直接按答案组均值训练。',
        '- joint_relations：另加题目百分比、时间单位、剩余量、差值、频率和计数条件与数值特征的交互，并使用去重logmeanexp目标。它是规则特征，不是完整语义求解器。', '',
        '组级模型只比较可解析答案，训练标签为唯一正确数值答案组；多个正确候选不再重复贡献正类概率。原候选目标仍包含无法解析候选作为负例，这是训练协议差异之一。推理统一屏蔽无法解析候选。', '',
        '每个家族先按alpha=0的验证准确率选择权重，同分比较自身验证目标损失；再比较固定alpha=0.25。本轮未为每个模型另外调票数奖励。', '',
        '## 训练与选定配置', '',
        'CPU四线程，全批量Adam，学习率0.03，零初始化，种子2026。除控制组外，预设L2=0.001/0.01/0.1，检查120/360轮。均值和标准差仅在训练数据上拟合，导出时折叠进权重。', '',
        '| 家族 | 输入 | 池化 | L2 | 轮次 | 验证独立正确 | 固定融合正确 |','|---|---|---|---:|---:|---:|---:|']
    for n,a in f['selected'].items():lines.append(f"| {n} | {a['input']} | {a['pool']} | {a['l2']} | {a['epoch']} | {a['validation_correct']['0.0']} | {a['validation_correct']['0.25']} |")
    lines += ['', '## 训练内部稳定性检查', '',
        f"按独立验证成绩选定组分支{f['group_branch']}、联合分支{f['joint_branch']}，再用训练题做3次80/20划分（种子17、29、43）。每次标准化、模型拟合只用80%，与同一80%重新训练的固定文本基线比较。", '',
        '这些划分相互重叠，模型配置此前已使用外部验证集选择，因此是诊断，不是三个独立最终测试，也不是无偏嵌套交叉验证。基线为原文本单模型加0.25奖励，不是前轮三模型融合。', '',
        '| 划分种子 | 留出题数 | 文本基线正确 | 方法 | alpha | 正确 | 修正基线 | 破坏基线 |','|---:|---:|---:|---|---:|---:|---:|---:|']
    deltas={}
    for split in t['stability']:
        for family,values in split['methods'].items():
            for alpha,a in values.items():
                lines.append(f"| {split['seed']} | {split['held_questions']} | {split['baseline_correct']} | {family} | {alpha} | {a['correct']} | {a['fixed']} | {a['broken']} |")
                deltas.setdefault(family+' alpha='+alpha,[]).append(a['correct']-split['baseline_correct'])
    lines += ['', '三次相对基线正确数净变化：']
    for key,value in deltas.items():lines.append(f"- {key}：{value}，平均{sum(value)/len(value):+.2f}题。")
    lines += ['', '## 重采样与简单组合', '',
        '两个选定分支各保留三个80%训练子集的模型，部署时平均标准化分数。每个成员及其统计量全部计入资产。不能把集成在这些重叠留出集上的预测当独立验证，因为其他成员可能见过对应题目；本轮没有这样报告集成留出成绩。', '',
        '简单组合比较组分支＋联合分支、组分支＋原文本控制两种搭配，组分支权重预设0.25/0.5/0.75，仅按验证alpha=0选择权重；同一权重再比较固定0.25奖励。每个成员的组内中心化分数尺度仅用训练输入计算，不用验证/测试拟合。', '',
        '## 官方评测及资源', '', '| 方法 | 验证集 | 测试集 | 资产KiB | 测试完整CPU耗时 |','|---|---:|---:|---:|---:|']
    for n,v in r['evaluations']['validation'].items():
        test=r['evaluations']['test'][n];audit=r['compliance'].get(n);size=f"{audit['asset_bytes']/1024:.2f}" if audit else '历史资产'
        lines.append(f"| {n} | {v['correct']}/798（{v['accuracy']:.4f}%） | {test['correct']}/467（{test['accuracy']:.4f}%） | {size} | {test['fresh_prediction_plus_scoring_seconds']:.3f}秒 |")
    lines += ['',f"按验证推荐：{chosen['method']}；模型文件{chosen['method_file']}；checkpoint={chosen['checkpoint']}。推荐在打开测试评分前保存。平分保留已有方法，不因其他方法测试更高改选。", '',
        '## 验证错误变化', '', '| 方法 | 对前轮验证推荐修正/破坏 | 对原文本单模型修正/破坏 | 分歧题正确/355 | 平票正确/88 |','|---|---:|---:|---:|---:|']
    for n,a in r['validation_groups']['all']['methods'].items():
        p=a['vs_previous_validation_choice'];q=a['vs_previous_single_text'];d=r['validation_groups']['answer_disagreement']['methods'][n];tie=r['validation_groups']['tied_leaders']['methods'][n]
        lines.append(f"| {n} | {p['fixed']}/{p['broken']} | {q['fixed']}/{q['broken']} | {d['correct']} | {tie['correct']} |")
    lines += ['', '## 限制审计', '',
        f"训练、重训与导出内部耗时{t['seconds_excluding_startup_imports']:.3f}秒，不含解释器启动和导入。硬件{r['hardware'].get('cpu_name','unknown')}，CPU四线程。", '',
        f"所有变体16MiB资产检查：{all(a['asset_limit_pass'] for a in r['compliance'].values())}；本机完整30秒检查：{all(a['local_time_limit_pass'] for a in r['compliance'].values())}；官方发布文件未变：{r['official_files_unchanged']}。", '',
        '完整计时包括新预测进程与独立评分进程的启动、导入、加载和全部成员/特征计算，每项一次。尚未在课程参考Xeon实测，最终资格以课程评测为准。', '',
        '无外部数据、额外预训练权重、参考答案推理读取、ID查表或缓存预测。拟合仅用训练输入/参考；验证用于开发选择；全部变体固定并保存哈希后才评分测试。未根据测试错误回头构造规则。推理仅NumPy，无GPU或API。', '',
        '## 解释边界与复现', '',
        '归一化答案组目标改变了重复候选的训练权重，也改变了无效候选的处理，不能把差异只归因于投票。平均、最大值和logmeanexp池化分别保留不同信息，没有保证哪一种必胜。线性交互并不等于完整推理验证。', '',
        '同一验证集已多轮开发，微小增益可能不稳定。内部划分与重采样用于补充证据，不消除所有选择偏差。详见DIRECT_GROUP_EXPERIMENTS.md。', '',
        'AI辅助披露：代码、实验与报告由Codex辅助完成，最终作者需理解核查并披露实质性帮助。']
    lines += ['', '## 本轮结论', '',
        '按预定规则选出的组合是group_joint_mix_valid_only：验证750/798=93.98%，测试382/467=81.80%。它是logmeanexp答案组模型与联合均值组模型各0.5的标准化分数组合。相对前轮验证推荐，验证修正6题、破坏5题，净增仅1题；测试未同步提高。不能把这1题视为稳定提升。', '',
        'joint_group_valid_only固定版本的验证为746/798=93.48%，测试391/467=83.73%，是本轮一个值得保留的观察结果，但并非按本轮验证规则选出的版本。本轮不因看到测试排名而替换推荐。85%目标仍未达到。', '',
        '直接去重logmeanexp组模型独立验证743，与候选控制持平；添加固定票数奖励后747，仅比控制746多1题。平均和最大池化未显示一致优势，不能认为去除候选重复计数必然改善泛化。', '',
        '联合模型不加额外奖励时比加0.25通常更好，说明已学到的票数交互可能与额外固定奖励重复。题目条件特征没有超过联合均值模型。', '',
        '内部稳定性证据不足：组模型加0.25相对基线净变化为[-5,+4,-9]，联合组模型不加额外奖励为[-6,+4,-3]，都不是跨划分一致提升。它们与验证集的微小增益相冲突，应保留这种不确定性。重采样和组合在当前验证排名下也不能自动视为更可靠。', '',
        '更有依据的后续是先制定训练内部稳定性筛选规则，再做外部验证排名，而不是继续无边界微调同一验证集。本轮没有在看过测试后重新选模型或修改参数。', '',
        '所有22变体通过冻结哈希、0/1/7题输入、未知ID、候选重排检查；控制模型逐题复现原文本模型。推理不加载PyTorch，官方发布文件未改。']
    failure_path=out/'failed-attempt.json'
    if failure_path.exists():
        failure=read(failure_path)
        lines += ['', '## 开发失败记录与额外成本', '',
            f"训练前半段曾因联合特征float64与权重float32不一致失败，失败日志保留为training-failed-dtype.log；按日志创建/末写时间估算该次壁钟耗时约{failure['approx_log_wall_seconds']:.2f}秒。统一特征为float32并补充类型及有效答案组池化一致性检查后完整重跑。", '',
            f"成功流程内部耗时{t['seconds_excluding_startup_imports']:.2f}秒；加上失败尝试约为{t['seconds_excluding_startup_imports']+failure['approx_log_wall_seconds']:.2f}秒，两个计时口径不同，合计仅为近似成本，不含所有启动/检查开销。失败发生在冻结和测试评分之前，不计作方法结果。"]

    (out/'REPORT.md').write_text(chr(10).join(lines)+chr(10),encoding='utf-8')
    summary=Path('EXPERIMENT_SUMMARY.md');old=summary.read_text(encoding='utf-8') if summary.exists() else '# 实验总结'
    marker='## 第七轮追加：直接组训练与联合共识';old=old.split(marker)[0].rstrip()
    appendix=['',marker,'',f"按验证选定{chosen['method']}。以下测试只记录固定版本，不用来改选。",'',
        '| 方法 | 验证正确/798 | 测试准确率 |','|---|---:|---:|']
    for n,v in r['evaluations']['validation'].items():appendix.append(f"| {n} | {v['correct']} | {r['evaluations']['test'][n]['accuracy']:.2f}% |")
    appendix += ['',f"本轮内部稳定性净变化：{deltas}。完整报告见runs/direct_group_round/REPORT.md。"]
    appendix += ['', '### 实际结果与下一步依据', '',
        '本轮预定验证推荐组合为750/798，但固定测试为382/467=81.80%，未获得同步提升。联合组均值模型固定版本测试391/467=83.73%，但验证746题，未按规则选中；不据测试排名事后换模型。', '',
        '训练内部三次划分中，答案组模型加投票净变化[-5,+4,-9]，联合组模型无额外投票[-6,+4,-3]，缺少稳定改进证据。下一阶段应先定义训练内稳定性筛选，再使用外部验证集排名；不能把单题验证增益当成可靠进步。', '',
        '22个变体的资产与本机四线程完整时间均符合上限，控制模型逐题复现原文本结果。参考CPU尚未实测。成功搜索约108秒，另保留约48秒的开发失败尝试成本。']

    summary.write_text(old+chr(10)+chr(10).join(appendix)+chr(10),encoding='utf-8')
    print(out/'REPORT.md');print(summary)


if __name__=='__main__':main()
