# 贡献指南 / Contributing

感谢你愿意参与。这个项目最看重的一件事是：**诚实**。

## 核心原则

> 宁可让一个结论被推翻，也不要让一个错误结论留在报告里。

本项目开发过程中出现过三个引擎缺陷，每一个都足以让回测结论**完全反转**。
它们之所以能被修复，是因为每一次修复都配了一条**回归测试**。

因此，任何涉及引擎行为的改动，都必须：

1. 同时新增或更新 `tests/test_regressions.py` 中的回归测试
2. 在 PR 描述里写清楚：这个改动会影响哪些已有结论
3. 如果结论变了，明确写出「旧结论 → 新结论」，并说明原因

## 开发流程

```bash
git clone https://github.com/aazh2026/vlab.git
cd vlab

# 跑测试（无需安装依赖，无需联网）
python3 -m unittest discover -s tests -v

# 抓取行情数据
PYTHONPATH=src python3 -m vlab fetch

# 生成回测报告
PYTHONPATH=src python3 -m vlab report

# 启动本地面板
PYTHONPATH=src python3 -m vlab serve
```

## 代码规范

- **零第三方依赖**：核心模块（`engine` / `metrics` / `report`）只允许使用 Python 标准库
- **不引入未来信息**：策略函数只能看到当日及之前的数据；成交价必须是成交日价格
- **不归一化超额权重**：未上市资产的权重必须留在现金，而不是挤到其他资产上
- 每个公开函数写 docstring，标注单位（小数还是百分数）

## 提交信息

用祈使句描述变更，例如：

- `fix(engine): keep excess weight in cash instead of re-normalising`
- `test: pin money-market yield synthesis against the 1.8% APY floor`
- `feat(report): add drawdown episode table`

## 免责声明

本项目仅供研究与教学使用。提交任何数据或结论时，请确认已经注明
**回测不预示未来收益，不构成投资建议**。

## Code of Conduct

请友善、就事论事。对观点的批评针对观点本身，不针对人。
