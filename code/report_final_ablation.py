"""Compile fixed-B ablations and verify new bundles; do not select a model."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import copy,json,hashlib,zipfile
from pathlib import Path
import numpy as np
from common import load_inputs,parse_answer
from evidence_models import predict
from run_fusion_experiments import labels
SRC=Path('runs/evidence_round');OUT=Path('runs/final_ablation')
def load(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    freeze=load(OUT/'freeze.json');mainfreeze=load(SRC/'freeze.json');sel=load(SRC/'selection.json')
    oldres=load(SRC/'official-results.json');newres=load(OUT/'official-results.json')
    rows=[]
    definitions=[
      ('none','joint',SRC,0,'复用'),
      ('S','joint_residual_semantic_r3',SRC,28,'复用'),
      ('V','joint_residual_verify_r3',SRC,22,'复用'),
      ('R','R_only',OUT,20,'补充'),
      ('S+V','joint_residual_both_r3',SRC,50,'复用'),
      ('S+R','SR_without_direct_V',OUT,48,'补充'),
      ('V+R','VR_without_direct_S',OUT,42,'补充'),
      ('S+V+R (B)','joint_residual_relative_r3',SRC,70,'复用'),
      ('S+V+R, no backbone','evidence_only_alpha0',OUT,70,'复用拟合/补充alpha控制')]
    bank,arr=load_inputs('validation');y=labels(bank,'validation')
    controls={};perquestion={}
    for block,n,src,dim,origin in definitions:
        v=(newres if src==OUT else oldres)[n];f=(freeze if src==OUT else mainfreeze)['variants'][n]
        c=f['oof_correct'] if src==OUT else sel['records'][n]['oof_correct']
        pred=load(src/'official'/n/'validation-predictions.json')['selected']
        perquestion[n]=y[np.arange(len(y)),pred].astype(bool)
        rows.append({'block':block,'variant':n,'origin':origin,'direct_dimensions':dim,
          'oof_correct':c,'validation_correct':v['validation']['correct'],'test_correct':v['test']['correct'],
          'test_accuracy':v['test']['accuracy'],'test_complete_seconds':v['test']['fresh_prediction_plus_scoring_seconds'],
          'asset_bytes':f['asset_bytes']})
    b=perquestion['joint_residual_relative_r3']
    for r in rows:
        v=perquestion[r['variant']]
        r['B_vs_variant_validation']={'fixed':int((b&~v).sum()),'broken':int((~b&v).sum())}
    # Check all newly frozen inference bundles and removed coefficient blocks.
    assert 'torch' not in __import__('sys').modules
    checked={}
    slices={'semantic':slice(0,28),'verify':slice(28,50),'relative':slice(50,70)}
    plan=load(OUT/'plan.json')
    for n,v in freeze['variants'].items():
        bundle=OUT/'variants'/n/'model_bundle'
        for p,h in v['assets'].items():assert digest(bundle/p)==h
        assert sum(p.stat().st_size for p in bundle.iterdir())==v['asset_bytes']<16*2**20
        with zipfile.ZipFile(bundle/'member0.npz') as z:assert all(i.compress_type==zipfile.ZIP_STORED for i in z.infolist())
        with np.load(bundle/'member0.npz',allow_pickle=False) as asset:
            if n in plan['new_subsets']:
                for k,keep in plan['new_subsets'][n].items():
                    if not keep:assert np.all(asset['e_weight'][slices[k]]==0)
        for size in (0,1,7):
            choices=predict(bank[:size],{'embeddings':arr['embeddings'][:size]},bundle)
            assert len(choices)==size and all(type(j) is int and 0<=j<4 for j in choices)
        small=copy.deepcopy(bank[:7]);ea=arr['embeddings'][:7];p=predict(small,{'embeddings':ea},bundle)
        assert p==load(OUT/'official'/n/'validation-predictions.json')['selected'][:7]
        for x in small:x['id']='new-id-'+x['id']
        assert p==predict(small,{'embeddings':ea},bundle)
        perm=np.array([2,0,3,1]);permuted=copy.deepcopy(small)
        for row in permuted:
            row['candidates']=[copy.deepcopy(row['candidates'][int(j)]) for j in perm]
            for j,c in enumerate(row['candidates']):c['index']=j
        pp=predict(permuted,{'embeddings':ea[:,perm]},bundle)
        for i,(j,k) in enumerate(zip(p,pp)):assert parse_answer(small[i]['candidates'][j]['text'])==parse_answer(permuted[i]['candidates'][k]['text'])
        fake=[{'id':'new','question':'unknown','candidates':[{'index':j,'text':'unknown'} for j in range(4)]}]
        assert predict(fake,{'embeddings':np.zeros((1,4,1024),np.float32)},bundle)==[0]
        checked[n]={'interface':True,'masked_weights_zero':True,'serialized_prediction_match':True,'assets':True}
    # All historical source and B asset hashes still match their original freeze.
    for p,h in mainfreeze['source_sha256'].items():assert digest(Path(p))==h
    bb=SRC/'variants'/'joint_residual_relative_r3'/'model_bundle'
    for p,h in freeze['B_assets_sha256'].items():assert digest(bb/p)==h
    manifest=load(Path('PACKAGE_MANIFEST.json'))
    for p,h in manifest['files'].items():assert digest(Path('..')/p)==h
    maxsec=max(v['test']['fresh_prediction_plus_scoring_seconds'] for v in newres.values())
    assert maxsec<30
    save(OUT/'checks.json',{'new_variants':checked,'NumPy_only_inference':True,'original_20_files_unchanged':True,
      'B_and_original_frozen_sources_unchanged':True,'max_new_test_seconds':maxsec,'local_limits_passed':True,
      'reference_Xeon_not_measured':True,'all_new_sources_sha256':{p:digest(Path(p)) for p in plan['source_sha256']}})
    save(OUT/'ablation-results.json',{'rows':rows,'post_hoc':True,'selection_changed':False})
    lines=['# 最终模型B：完整消融整理','',
      'B=joint_residual_relative_r3。主干/权重/既有选模与评分记录未改动。本表由已有严格匹配对照和本次补充实验组成，属于事后解释性分析，不据此重选B。','',
      '## 1. 对照定义与控制变量','',
      '主干为1070维joint线性模型（1024固定向量+22旧文本/数值+24共识交互）；答案组平均，alpha=0。S=28维条件/目标，V=22维局部检验，R=20维候选相对证据。残差主实验均保持相同主干、训练分折、折内标准化、L-BFGS预算及L2=.03。',
      '新补充R、S+R、V+R三个直接输入子集，21次折内/全量残差拟合；复用既有7套折内/全量主干，不重训B。另把旧独立证据模型固定alpha=0，消除此前alpha=.25的混杂，未新增该模型训练。',
      '删除输入块时保留70维布局，训练对应列置零，确认对应权重精确为零；推理仍使用原特征实现且系数为零。因此计时并未省掉被屏蔽特征的提取成本，不能由此推断裁剪工程实现的加速收益。',
      '**信息依赖边界：R由S/V相关元信息派生；无直接S/V不等于系统完全不含语义/算术信息。旧主干也有文本/数值特征。此表是直接输入块消融，不是各类信息来源的完全隔离。**','',
      '## 2. 全部直接输入子集与无主干控制','',
      '| 直接证据块 | 维数 | 两套OOF正确/4755 | 验证/798 | 固定测试/467 | 测试% | B相对该行验证修复/破坏 |',
      '|---|---:|---|---:|---:|---:|---|']
    for r in rows:
        fb=r['B_vs_variant_validation']
        lines.append(f"| {r['block']} | {r['direct_dimensions']} | {r['oof_correct']} | {r['validation_correct']} | {r['test_correct']} | {r['test_accuracy']:.4f} | {fb['fixed']}/{fb['broken']} |")
    lines+=['','OOF两套预测相关，不能按9510个独立题解释。训练OOF与验证已多次开发使用；本次补充也不是新的独立泛化评估。测试记录不用于调整超参数或改变最终方案。','',
      '## 3. 可据此支持的结论','',
      '- 完整B相对旧joint主干，OOF增24/40题，验证+5，固定测试+10；新增证据确实补充了旧主干，但不说明每一步推理得到正确验证。',
      '- 删除R（B→S+V），OOF减少6/20题、验证少4、测试少7；这是相对证据输入最清楚的匹配证据。',
      '- 删除直接V（B→S+R），OOF两套各少4题、验证少1、测试少3，支持V作为辅助。',
      '- 删除直接S（B→V+R），第一套OOF反而多2题，第二套少14题；验证少3、测试少2。因此S的收益存在划分敏感性，不能声称各划分都有效。',
      '- R单独作为新增残差输入已有信号；完整三块的增益不能解释为“条件、算术和比较三个独立能力”的简单加和。',
      '- 同样alpha=0的独立证据模型远低于B；当前规则证据无法替代固定向量主干。','',
      '## 4. 结构、正则与组合的已有对照','',
      '| 比较 | 两套OOF正确数 | 验证/798 | 固定测试/467 |',
      '|---|---|---:|---:|']
    for n in ['joint_residual_relative_r3','joint_residual_relative_r10','joint_refit_relative_r3','joint_refit_relative_r10',
               'joint_gated_5','joint_gated_10','no_style_residual_relative_r3','new_pair_50','new_pair_75','new_triple','no_style_evidence_90']:
        r=sel['records'][n];v=oldres[n]
        lines.append(f"| {n} | {r['oof_correct']} | {v['validation']['correct']} | {v['test']['correct']} |")
    lines+=['','重训vs冻结残差同时改变了优化器（Adam vs L-BFGS）及训练参数范围，不能将差异完全归因于冻结。门控也改变了作用题目与修正幅度。跨主干对比不是单因素因果实验。两档正则、门控和融合都是此前固定搜索，不能利用测试排名事后宣称新的最优配置。','',
      '## 5. 发展路线与严格消融的区别','',
      '报告可将“多数票→向量评分→轻量投票/文本→答案组训练→证据残差”作为发展路线。历轮改变目标、输入、优化和选择协议，不应把它们全部称为严格逐项增益。严格归因优先使用上面的固定主干八子集表。',
      '最终B不属于去格式主干，旧22维特征仍包含长度、格式与置信措辞。历史去格式实验只能提供背景，不能证明B完全不依赖表面特征。此轮未额外引入新的结构搜索。','',
      '## 6. 可复现命令与资源','',
      '在Anaconda Prompt中，进入code/，激活mp1，设置OMP_NUM_THREADS、OPENBLAS_NUM_THREADS、MKL_NUM_THREADS为4：',
      '1. python -X utf8 -B supplement_final_ablation.py --stage freeze',
      '2. python -X utf8 -B supplement_final_ablation.py --stage evaluate',
      '3. python -X utf8 -B report_final_ablation.py',
      'freeze阶段依赖runs/evidence_round的原始折内主干、特征缓存、folds和独立证据资产；这些是实验复用材料，不是B推理依赖。已冻结目录不要重跑freeze，直接evaluate（会跳过已评分项）或report。',
      '详细冻结、每次拟合、官方预测/评分及接口检查见runs/final_ablation/。补充实验仅作解释，记录中保留了已见测试后的时间顺序。','',
      '| 变体 | 推理资产字节 | 新预测+独立评分秒 |','|---|---:|---:|']
    for r in rows:lines.append(f"| {r['variant']} | {r['asset_bytes']} | {r['test_complete_seconds']:.3f} |")
    lines+=['','本地Windows i9-12900H、CPU4、NumPy2.5.3/PyTorch2.7.1。参考Xeon未测。21次新残差拟合之外，没有重跑原有主干/已完成消融；新资产和接口检查通过，官方20文件及B保持原样。','',
      '## 7. 报告使用建议','',
      '正文放本表的旧主干、S、V、S+V、B五行，再以B−S/B−V/B−R三行补足反向对照；R和无主干控制可并表或简述。避免只选有利行。正文给出OOF与验证证据，测试注明为固定版本记录。详细表、命令和hash保留仓库，正文总页数不超过10页。',
      'AI披露与来源见AI_DISCLOSURE.md；写作结构见REPORT_OUTLINE.md。']
    text='\n'.join(lines)+'\n'
    Path('FINAL_MODEL_ABLATION.md').write_text(text,encoding='utf8')
    (OUT/'REPORT.md').write_text(text.replace('](runs/','](../'),encoding='utf8')
    save(OUT/'report-integrity.json',{'report_sha256':digest(Path('FINAL_MODEL_ABLATION.md')),'new_official_variants':len(newres),'total_feature_subsets':8,'new_residual_fits':21})
    print(json.dumps({'rows':rows,'checks_passed':len(checked),'B_unchanged':True},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
