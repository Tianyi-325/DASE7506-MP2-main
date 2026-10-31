# 优先级优化：复现与限制检查

## 环境

使用已有mp1，训练CPU四线程，最终推理只需NumPy。无需新依赖或外部模型。

~~~bat
conda activate mp1
cd /d E:\DASE7506-MP2-main\code
set OMP_NUM_THREADS=4
set OPENBLAS_NUM_THREADS=4
set MKL_NUM_THREADS=4
~~~

## 从头复现

~~~bat
python check_refinements.py
python train_refinements.py --output runs/refinements_reproduction
python evaluate_refinements.py --output runs/refinements_reproduction
python report_refinements.py --output runs/refinements_reproduction
~~~

训练拒绝覆盖已有freeze.json目录。训练阶段只读训练和验证集。评测先校验冻结源码和资产，再运行官方验证/测试评分。完整流程依赖上一轮runs/remaining_directions/中的文本、算式和纯向量线性模型作为基础/参照；新部署bundle自包含，不依赖那些路径。

## 直接复现推荐模型

查看runs/priority_refinements/validation-recommendation.json中的method_file与checkpoint。若推荐previous，继续使用上一轮remaining_models.py与对应资产。若推荐新模型，使用refinement_models.py：

~~~bat
python predict.py --method refinement_models.py --checkpoint runs/priority_refinements/CHOSEN_VARIANT/model_bundle --split validation --output runs/reproduce-validation.json
python score_predictions.py --split validation --predictions runs/reproduce-validation.json --output runs/reproduce-validation-score.json
~~~

CHOSEN_VARIANT替换为推荐名称。测试将split和输出文件名改为test。audit使用相同模型加--split audit --data-dir实际输入目录，不重新训练或读取参考答案。

## 折外过程与选择

五折按训练题目划分，同题候选不拆分；每折标准化与基础模型只拟合其他四折。基础配置沿用上一轮，不在折外过程中看验证标签调参。15次基础模型拟合后，融合器使用训练集折外分数拟合。ID只用于训练记录对齐，不进入推理。

融合与答案组模型以小网格验证选择；文本块正则化、联合目标、配对、难题加权、TF-IDF同样使用预设网格。各单评分器先按无额外投票奖励的验证准确率选权重，再评测固定alpha=0.25；simple_blend单独预设了6组权重与3个alpha。具体记录在validation-search.csv。

## 记录

runs/priority_refinements/：

- REPORT.md：方法、全部成绩、错误变化及限制。
- freeze.json：选定配置、源码和资产SHA256。
- training-results.json、training-curves.csv、validation-search.csv：搜索成本及全部记录。
- oof-split.json、oof-training-scores.npz：训练诊断材料，不在推理路径中。
- validation-recommendation.json：只依据验证结果选定的推荐。
- experiment-results.json：官方JSON成绩、CPU硬件/时间、资产限制与原始文件完整性检查。
- validation-cases.json：逐题验证选择和正确性变化。
- 各变体目录：自包含model_bundle、官方预测/评分JSON、进程日志。

模型资产包含所有基础系数、IDF、缩放统计、元模型权重与配置，按未压缩总字节计入16MiB。完整耗时包含新预测及独立评分进程的启动、导入、加载和全部预处理。所有库设置4线程。仍需课程参考CPU最终认证。

无外部数据、额外预训练权重、缓存答案、ID查表、推理生成或API。TF-IDF只拟合训练候选，数字身份被统一标记。算式检查沿用白名单AST实现，不执行候选代码。