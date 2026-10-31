# 充分训练尝试：操作与复现

本轮仅改变组内线性模型的训练时长和学习率调度，沿用已有向量、数据划分、标准化、多正例目标和推理实现。无新依赖，无GPU训练。

## 环境

在Anaconda Prompt中：

~~~bat
conda activate mp1
cd /d E:\DASE7506-MP2-main\code
set OMP_NUM_THREADS=4
set OPENBLAS_NUM_THREADS=4
set MKL_NUM_THREADS=4
~~~

## 从头复现并保留当前结果

~~~bat
python train_long_group.py --output runs/long_training_reproduction
python evaluate_long_group.py --output runs/long_training_reproduction
python report_long_group.py --output runs/long_training_reproduction
~~~

训练会拒绝覆盖已有freeze.json的目录。训练只读训练/验证数据与参考；评测会先校验源码和模型哈希，再运行官方验证和测试评分。报告不影响配置选择。评测依赖上一轮runs/vector_objectives/中的冻结模型作为对照。

搜索范围：L2=0.0001、0.001、0.01；constant学习率0.01；cosine学习率从0.03到0.00001；最长3000轮；仅360、1000、3000轮进入验证选择。全批量Adam，CPU四线程，零初始化，种子2026。选择标准为独立屏蔽后验证准确率，再比较验证组内损失。固定alpha=0.25的融合仅作为同一评分器的第二种推理策略，不据融合成绩另选权重。

## 直接使用本轮长训练资产

~~~bat
python predict.py --method vector_vote_fusion.py --checkpoint runs/group_long_training/weighted/model_bundle --split validation --output runs/group_long_training/long_weighted/validation-predictions.json
python score_predictions.py --split validation --predictions runs/group_long_training/long_weighted/validation-predictions.json --output runs/group_long_training/long_weighted/validation-score.json
~~~

测试时将split与输出文件名中的validation改为test。移除投票奖励则使用valid_only/model_bundle。本轮最终推荐应查看validation-recommendation.json：若验证结果未超过原模型，可能仍推荐上一轮资产。不要默认长训练必然更好。

## 输出记录

目录runs/group_long_training/：

- REPORT.md：中文结果报告。
- training-results.json、training-curves.csv：训练损失、含L2损失、梯度、权重范数和学习率。
- validation-search.csv：18个预设验证检查点。
- training-process.log、progress.json：训练运行日志及进度。
- freeze.json：选定训练配置、源码/资产SHA256。
- validation-recommendation.json：仅依据验证成绩决定是否保留新模型。
- experiment-results.json：官方成绩、分组错误变化、硬件与完整外部CPU计时。
- validation-cases.json：逐题验证选择变化。
- valid_only/model_bundle、weighted/model_bundle：两个策略的独立推理资产。
- previous_*、long_*：官方预测/评分JSON和进程日志。

推理仅依赖NumPy，不需要PyTorch或重新训练，可直接接受新audit输入。