# 向量评分实验使用说明

本轮方法是 vector_logistic.py，不修改官方 submission.py 空接口、解析器或评分器。官方 runner 使用 --method 选择本轮实现。

## 已有 mp1 环境

从 Anaconda Prompt 执行：

~~~bat
conda activate mp1
cd /d E:\DASE7506-MP2-main\code
set OMP_NUM_THREADS=4
set OPENBLAS_NUM_THREADS=4
set MKL_NUM_THREADS=4
~~~

无需重新安装。新环境可使用 Python 3.12 并安装 requirements-vector.txt；PyTorch 仅供训练和诊断，NumPy 即可完成官方预测与评分。

## 仅复现已冻结模型

~~~bat
python predict.py --method vector_logistic.py --checkpoint runs/vector_logistic/model_bundle --split validation --output runs/vector_logistic/vector/validation-predictions.json
python score_predictions.py --split validation --predictions runs/vector_logistic/vector/validation-predictions.json --output runs/vector_logistic/vector/validation-score.json
~~~

测试命令把 split 和输出文件名中的 validation 改为 test。audit 输入使用相同模型和 --split audit --data-dir 对应目录，无须重训。

## 从头训练或完整评测

~~~bat
python train_vector.py --output runs/vector_reproduction
~~~

该命令只读训练/验证输入和参考，输出九组验证结果及选定资产。使用新输出目录可保留本轮实验。evaluate_vector.py 固定评测 runs/vector_logistic 中的冻结模型，不自动切换到新训练目录。

~~~bat
python evaluate_vector.py
~~~

完整评测会先验证本轮资产和训练/推理源文件哈希，再在独立进程运行基线及向量模型的验证集和测试集预测/评分，记录外部耗时和硬件，并生成验证集诊断。重复执行会覆盖本轮评测 JSON，运行时间可变化。REPORT.md 是首次运行记录，不会自动重写。

输出位置：runs/vector_logistic/；详见 REPORT.md、training-results.json、experiment-results.json、freeze.json。runs/ 被 .gitignore 忽略，发布时需单独打包上传所需资产及记录。
