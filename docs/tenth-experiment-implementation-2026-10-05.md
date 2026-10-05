# 第十轮实施计划

前提：Phase A验收EXP-174完成，fix commit3751f9d已创建；读取同日冻结设计与参数卡。

1. 实现独立`models/leader_allocation.py`：严格输入校验、闭合动量、Top-1与因果expanding分位数，输出四列targets及审计。
2. 关键行为检查先行：未来数据扰动不影响prefix、当前点不进入自身分位数、缺口不恢复、favorable与父策略不变、25%邻域等于父策略；不修改引擎／风险以追候选收益。
3. 实现受控脚本入口：只读旧概率／状态与开发数据，绑定修复后的父策略和Phase A验收及所有源SHA，登记唯一目录、保存配置／源码／环境／CSV／JSON与失败；目标及账本无标签字段。
4. 事前登记9Base及选择，执行EXP-176～185；基础失败停止压力。只有实际合格胜出候选才能运行冻结6压力和复用25%邻域。
5. EXP-192输出相对修复R0/R5/R6差异、每币／状态贡献、Alpha与ordinary生命周期收益分布、年份与规则稳定性及过拟合限制，回答12项交付问题。
6. 更新AGENTS／STATUS／DECISIONS／EXPERIMENTS／WORKLOG／README，压缩保留可审计新流水（不含2026行情或凭据），提交、推送分支并创建GitHub PR。当前未执行步骤，以STATUS实际记录为准。
