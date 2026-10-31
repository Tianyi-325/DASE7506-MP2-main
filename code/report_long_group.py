"""Recreate CSV records and Chinese report for the long-training experiment."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('runs/group_long_training'))
    args=parser.parse_args();out=args.output
    training=json.loads((out/'training-results.json').read_text())
    freeze=json.loads((out/'freeze.json').read_text())
    result=json.loads((out/'experiment-results.json').read_text())
    recommendation=json.loads((out/'validation-recommendation.json').read_text())
    for filename,rows in [('training-curves.csv',training['curves'])]:
        with (out/filename).open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with (out/'validation-search.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(['schedule','l2','epoch','lr','validation_group_loss','valid_only_correct','weighted_correct','gradient_norm'])
        for r in training['checkpoints']:
            writer.writerow([r['schedule'],r['l2'],r['epoch'],r['lr'],r['validation_group_loss'],r['validation_correct']['valid_only'],r['validation_correct']['weighted'],r['gradient_norm_before_step']])
    selected=freeze['selected']
    lines=['# 第四轮：组内线性模型充分训练与学习率衰减', '',
           '## 目的与控制变量', '',
           '检验更长、更稳定的优化是否能提高已有组内线性评分器准确率。保持训练数据、1024维固定向量、训练集标准化、多正例组内目标、线性模型容量及推理规则不变；不增加文本/比较特征。', '',
           '全部使用CPU四线程、全批量Adam、零初始化、种子2026。两种调度各训练3个L2强度（0.0001、0.001、0.01）：constant固定学习率0.01；cosine从0.03余弦衰减到1e-5，总计3000轮。每条轨迹预定在360、1000、3000轮检查验证结果，其余时刻只记录训练曲线。', '',
           '总计6条轨迹、18000次优化更新、18个验证检查点。模型按屏蔽后独立评分的验证正确数选择，相同则取较低验证组内损失。同一个选定权重同时导出valid_only和weighted，后者alpha固定0.25，没有重新调参。测试参考从不参与训练/选择。', '',
           '## 全部验证检查点', '',
           '| 调度 | L2 | 轮次 | 当时学习率 | 独立正确数 | 固定融合正确数 | 验证组内损失 | 梯度范数 |',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in training['checkpoints']:
        lines.append(f"| {r['schedule']} | {r['l2']} | {r['epoch']} | {r['lr']:.6g} | {r['validation_correct']['valid_only']} | {r['validation_correct']['weighted']} | {r['validation_group_loss']:.6f} | {r['gradient_norm_before_step']:.6g} |")
    lines += ['',f"选定：{selected['schedule']}，L2={selected['l2']}，{selected['epoch']}轮；验证独立正确{selected['validation_correct']['valid_only']}题，固定融合正确{selected['validation_correct']['weighted']}题。选择记录及源码/资产哈希在测试评分前写入freeze.json。", '',
              '## 优化稳定性', '',
              '下表列出每条训练轨迹3000轮末的训练状态；梯度范数为最后一次更新前测量，损失与权重范数为更新后测量。较低梯度和趋于稳定的损失只代表局部优化趋稳，不保证泛化准确率提升，也不证明多正例目标已达到全局最优。', '',
              '| 调度 | L2 | 末学习率 | 训练组内损失 | 训练含L2损失 | 梯度范数 | 权重范数 |','|---|---:|---:|---:|---:|---:|---:|']
    for r in training['curves']:
        if r['epoch']==3000:
            lines.append(f"| {r['schedule']} | {r['l2']} | {r['lr']:.6g} | {r['train_data_loss']:.6f} | {r['train_regularized_loss']:.6f} | {r['gradient_norm_before_step']:.6g} | {r['weight_norm']:.4f} |")
    lines += ['', '## 固定版本的官方评测', '', '| 方法 | 验证集 | 测试集 | 验证完整CPU耗时 | 测试完整CPU耗时 |','|---|---:|---:|---:|---:|']
    for name,v in result['evaluations']['validation'].items():
        t=result['evaluations']['test'][name]
        lines.append(f"| {name} | {v['correct']}/{v['n']}（{v['accuracy']:.4f}%） | {t['correct']}/{t['n']}（{t['accuracy']:.4f}%） | {v['fresh_prediction_plus_scoring_seconds']:.3f}秒 | {t['fresh_prediction_plus_scoring_seconds']:.3f}秒 |")
    lines += ['',f"本轮验证推荐：{recommendation['method']}。与旧模型比较时，仅依据验证正确数，平分保留原模型。测试分数只作固定版本记录。", '',
              '## 验证分组与错误变化', '', '| 分组 | 题数 | 方法 | 正确数 | 准确率 | 相对原融合修正 | 相对原融合破坏 |','|---|---:|---|---:|---:|---:|---:|']
    for group,data in result['validation_groups'].items():
        for name,r in data['methods'].items():
            delta=r['vs_previous_weighted']
            lines.append(f"| {group} | {data['n']} | {name} | {r['correct']} | {r['accuracy']:.2f}% | {delta['fixed']} | {delta['broken']} |")
    previous=result['evaluations']['validation']['previous_weighted']
    new=result['evaluations']['validation']['long_weighted']
    net=new['correct']-previous['correct']
    lines += ['', '## 结论与解释边界', '',
              f"本轮选定长训练模型固定融合，相对上一轮融合验证净变化为{net:+d}题。应以这个验证结果判断是否保留；不能因测试表现更好或更差而改选检查点。", '',
              '长训练效果应同时考察损失、梯度、验证准确率。损失下降而准确率不升，并不矛盾：训练优化的是概率质量，官方指标是离散选择。增加轮次也无法直接补充线性模型缺少的非线性关系或题目/推理特征。', '',
              '这里只探索两种调度、三个正则化强度、零初始化。没有证明该方向的绝对上限。反复使用同一验证集进行开发可能造成选择乐观偏差，因此不应无边界继续细搜。当前固定alpha在不同logit尺度下的影响也需要与训练本身区分。', '',
              '训练充分性与泛化效果是不同问题；对多正例组内目标，训练可能存在不同局部解。未使用测试错误案例设计规则，未读取测试参考做参数选择。', '',
              '## 资源与复现', '',
              f"训练搜索内部耗时{training['search_seconds_excluding_startup_imports']:.3f}秒，包括数据加载和验证/导出，但不包括进程启动和导入。硬件：{result['hardware'].get('cpu_name','unknown')}；四线程CPU。", '',
              '| 新变体 | 资产字节 | MiB |','|---|---:|---:|']
    for name,size in result['asset_bytes'].items():
        lines.append(f'| {name} | {size} | {size/2**20:.6f} |')
    lines += ['', '推理只需NumPy，标准化折叠到系数。完整CPU计时为新预测进程加独立官方评分进程，包含启动、导入、加载；每项单次，本机数据不能直接认证参考Xeon资格。', '',
              '脚本：train_long_group.py、evaluate_long_group.py、report_long_group.py。详细复现见LONG_TRAINING_EXPERIMENT.md。记录包括训练日志、训练曲线CSV、验证搜索CSV、逐题验证变化、官方预测/评分JSON、配置与哈希。', '',
              'AI披露：本轮脚本、运行和报告由Codex辅助完成；最终提交需理解实现并披露实质性AI帮助。']
    maximum_secondary=max(r['validation_correct']['weighted'] for r in training['checkpoints'])
    lines += ['', '## 进一步判断', '',
              '余弦衰减在L2=0.001、0.01的3000轮末，梯度范数分别约6.6e-8和4.2e-8，说明至少这些轨迹已相当接近训练目标的驻点；验证独立正确数仍未超过选定的360轮模型。因此本轮没有证据支持继续单纯增加轮次。', '',
              f'全部检查点中，固定融合的最高验证正确数为{maximum_secondary}题；它是次要观察指标，不是本轮评分器选择依据。部分独立评分较低的检查点可能在固定融合下略高，不能据此事后改变预设规则。本轮结论针对预先定义的评分器选择流程，不等于宣布所有训练配置的融合上限。', '',
              '若后续改变模型容量、加入候选间比较或增加文本/计算信息，可能获得新的增益；这些属于新实验，不能由本轮未提升推断其无效。', '']

    (out/'REPORT.md').write_text(chr(10).join(lines)+chr(10),encoding='utf-8')
    print(out/'REPORT.md')


if __name__=='__main__':
    main()
