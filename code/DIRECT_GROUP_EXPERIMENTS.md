# 直接答案组与联合共识实验复现

## 环境

使用已有mp1，全部训练与推理均为CPU。无新依赖，推理只需要NumPy。

~~~bat
conda activate mp1
cd /d E:\DASE7506-MP2-main\code
set OMP_NUM_THREADS=4
set OPENBLAS_NUM_THREADS=4
set MKL_NUM_THREADS=4
~~~

## 完整复现并保留原记录

~~~bat
python check_direct_groups.py
python train_direct_groups.py --output runs/direct_groups_reproduction
python evaluate_direct_groups.py --output runs/direct_groups_reproduction
python report_direct_groups.py --output runs/direct_groups_reproduction
~~~

已有freeze.json的目录拒绝重训覆盖。评测依赖上一轮runs/priority_refinements/simple_blend_weighted和runs/remaining_directions/linear_text_weighted的冻结资产作为两种历史参照。新部署bundle自包含全部成员权重与分数缩放，不依赖那些参照路径。

## 方法

- control：固定原文本候选模型，L2=0.01、120轮。
- group_mean、group_max、group_logmeanexp：直接从原向量/文本训练不同答案组，比较均值、最大值、去重logmeanexp。
- joint_candidate：票数及数值性质交互联合训练，候选级目标。
- joint_group：同样联合特征，答案组均值目标。
- joint_relations：进一步加入题目条件×数值特征，使用去重logmeanexp目标。

每个非控制家族预设L2=0.001/0.01/0.1，120/360轮检查；Adam学习率0.03，零初始化。先按alpha=0验证正确数选权重，同分按原生验证目标损失；同一权重再比较固定alpha=0.25。所有特征float32，标准化仅由对应训练数据拟合并折叠进部署权重。

按独立验证准确率各选一个组分支和联合分支，用训练集做三次80/20诊断（种子17/29/43），每次基线与候选都只拟合同一80%。保留这两个分支的三个重采样模型组成平均集成；同时比较组分支＋联合分支、组分支＋文本控制的简单混合。分数归一化统计只用训练输入。

## 直接使用已训练资产

查看runs/direct_group_round/validation-recommendation.json中的method_file、checkpoint。若推荐旧版本，按指定旧文件运行；若推荐本轮新模型，使用：

~~~bat
python predict.py --method direct_group_models.py --checkpoint runs/direct_group_round/CHOSEN_VARIANT/model_bundle --split validation --output runs/direct-group-validation.json
python score_predictions.py --split validation --predictions runs/direct-group-validation.json --output runs/direct-group-validation-score.json
~~~

替换CHOSEN_VARIANT。测试将split与文件名的validation改为test；audit使用同一checkpoint并添加--split audit --data-dir实际输入目录，不重训。

## 记录与限制

runs/direct_group_round/包含REPORT.md、freeze.json、training-results.json、训练/验证CSV、内部稳定性记录、逐题验证变化、官方预测/评分JSON、硬件和完整CPU计时、模型资产哈希。每个部署目录包含所有成员，按未压缩字节计入16MiB，完整耗时计入所有成员与预处理。

如果有失败尝试，会保留失败日志和资源说明；未固定版本前不会开始测试评分。当前开发曾修正联合特征float64/float32拼接错误，增加特征类型和有效组池化数值一致性检查；失败记录不计作模型结果。

三次内部留出划分重叠，选定配置也已用验证集，因此是稳定性诊断，不是无偏嵌套交叉验证。不能把某个集成成员训练过的样本当作该集成的独立留出集；本轮不报告这种成绩。

无外部数据、额外预训练权重、ID查表、缓存预测或推理API。训练只拟合训练集，验证用于选择，测试在全部配置与哈希固定后记录。CPU最终资格仍需课程参考机器确认。