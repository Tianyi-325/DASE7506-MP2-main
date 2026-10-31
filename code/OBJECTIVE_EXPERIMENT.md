# 训练充分性与组内选择：复现说明

## 环境

使用已有mp1，无需安装新包。训练使用CPU PyTorch；官方预测与评分仅依赖NumPy。

~~~bat
conda activate mp1
cd /d E:\DASE7506-MP2-main\code
set OMP_NUM_THREADS=4
set OPENBLAS_NUM_THREADS=4
set MKL_NUM_THREADS=4
~~~

## 本轮记录

目录：runs/vector_objectives/。

- REPORT.md：报告。
- training-results.json：12条训练轨迹、36个验证检查点、监督结构与内部搜索耗时。
- training-curves.csv：训练损失、正则化损失与梯度范数。
- validation-search.csv：所有验证检查点结果。
- freeze.json：验证选定配置、推理资产与源码哈希、按验证集推荐的变体。
- experiment-results.json：官方验证/测试成绩、硬件、完整外部CPU耗时和分组错误变化。
- validation-case-comparisons.json：验证集全部逐题选择和正确性。
- validation-confidence.json：不同答案组分差与实际正确率。
- bce_valid_only、bce_weighted、group_valid_only、group_weighted：四个互斥变体，各有model_bundle、官方预测/评分JSON及进程日志。
- original_valid_only、original_weighted：本轮重新测量的上轮对照。

每种训练目标仅按valid_only验证准确率选择一个评分器，融合策略使用同一权重且alpha固定0.25，不重新调参。所有配置在测试评分前固定。

## 无须重训，直接使用资产

以下以group_valid_only为例，具体推荐变体查看freeze.json或REPORT.md。

~~~bat
python predict.py --method vector_vote_fusion.py --checkpoint runs/vector_objectives/group_valid_only/model_bundle --split validation --output runs/vector_objectives/group_valid_only/validation-predictions.json
python score_predictions.py --split validation --predictions runs/vector_objectives/group_valid_only/validation-predictions.json --output runs/vector_objectives/group_valid_only/validation-score.json
~~~

测试时将split与文件名中的validation改为test。对新audit输入，使用同一个模型并添加--split audit --data-dir实际输入路径；不重训，不读取参考。

## 从头复现，保留原目录

~~~bat
python check_objectives.py
python train_objectives.py --output runs/objectives_reproduction
python evaluate_objectives.py --output runs/objectives_reproduction
python report_objectives.py --output runs/objectives_reproduction
~~~

训练不会覆盖已有freeze.json的目录。评测与报告会覆盖目标目录中的相应结果，请使用新目录保留原计时。evaluate_objectives.py依赖上轮runs/vector_vote_fusion/中的冻结资产用于对照。

训练网格固定为学习率0.01、0.03，L2为0.0001、0.001、0.01，在120、360、1000轮检查验证结果。训练曲线只记录训练信息，验证选择仅使用预定检查点。导出后的模型不需要Torch运行，标准化已折叠进线性系数。

组内损失为logsumexp(all)−logsumexp(correct)，数值稳定，支持多个正确答案。全正确题的数据损失为0；这会改变有效训练监督量。两种损失的L2尺度并不严格可比；固定票数奖励在不同目标下也可能因logit尺度不同而表现不同。
