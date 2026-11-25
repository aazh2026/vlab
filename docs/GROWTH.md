# 增长手册 / Growth playbook

拿 100 star 的实际路径，按性价比排序。

## 前提：star 的两个来源

1. **被搜到**（SEO / GitHub Explore / topic 标签）—— 需要有人搜"backtesting"、"资产配置"、"A股"
2. **被推**（社交分享 / Hacker News / 掘金 / V2EX / 即刻）—— 需要有人读完觉得值得转

代码质量决定下限，**曝光**决定上限。这个仓库已经过了"能被搜到"的门槛
（README 有中英双语、有徽章、有在线演示、topic 标签齐全），现在缺的是曝光。

## 已完成

- [x] 中英双语 README，含真实数字表格
- [x] 在线演示（GitHub Pages）
- [x] 零依赖 + 零 CDN 徽章
- [x] CI 多 Python 版本绿灯
- [x] Issue 模板（bug / 策略请求 / 免责声明）
- [x] 社交预览图
- [x] `docs/POST_zh.md` —— 可直接发布的中文长文草稿
- [x] CONTRIBUTING 里写清"怎么加自己的策略"（降低参与门槛）

## 优先级清单

### P0 —— 一周内可做

1. **发布中文长文**
   渠道：V2EX（技术）、掘金（技术）、知乎（想法）、即刻（投资/独立开发）
   标题建议：
   - 「我写了个资产配置回测框架，然后发现它骗了我」
   - 「回测里那 5 个 bug，每一个都足以让结论完全反转」
   - 「为什么我不再相信没有测试的量化回测」

   贴 GitHub 仓库 + Pages 演示链接。**不要**贴收益承诺。

2. **加一个 `awesome-` 式的入口**：把 vlab 加进
   - [awesome-quant](https://github.com/wilsonfreitas/awesome-quant) 的 Portfolio Management 条目
   - [awesome-python](https://github.com/vinta/awesome-python) 的 Financial 相关条目
   - 英文的 [awesome-fintech](https://github.com/wshobson/awesome-fintech)
   这几个仓库 star 都在 10k+，被收录一次能带来几十到几百 star。

3. **给热门量化仓库提 PR**：加一个"Portfolio Backtesting"分类的链接。

### P1 —— 一到两周

4. **做一个可分享的 demo GIF**（15 秒：净值曲线 + 回撤 + 表格排序）
   放 README 顶部。GIF 对 star 转化率的影响远大于静态截图。

5. **在 Reddit 发**：
   - r/algotrading —— 发"我重构自己的回测框架，发现了 5 个让结论反转的 bug"
   - r/Python、r/fintech
   注意 Reddit 社区对"投资建议"非常敏感，标题和正文都要避开荐股。

6. **Hacker News**：标题要中性偏技术，不要营销腔。
   "Show HN: vlab – zero-dependency portfolio backtesting lab with regression tests for its own historical bugs"

### P2 —— 持续

7. **社区活动：「你的配置我来回测」**
   在 Discussions 开一个征集帖，让人报自己的资产配置权重，你用 vlab 跑出结果发回去。
   这个活动的价值不是 star，是**产生真实的使用案例和 Issue**，
   而真实案例是最好的 star 磁铁。

8. **把"房产 vs 持币"模块做出来**（原 TODO）。
   这是中文用户的独家需求，英文项目没有对标，天然有差异化。

9. **英文 README 单独优化**：英文社区更大，但要更简洁、更少"个人叙事"、
   更突出 API 和可复用性。

## 不要做的事

- ❌ 不要在标题/简介里承诺收益
- ❌ 不要发"推荐买入"式内容 —— 会招黑粉，且违背项目自己的免责声明
- ❌ 不要买 star。项目价值建立在"诚实的回测"上，买 star 会摧毁这个立意
- ❌ 不要为了 star 加一堆无用功能。**少而准 > 多而杂**（Steve Jobs 原则）

## 度量

看这几个数：
- Weekly stars（`gh api repos/aazh2026/vlab` 的 stargazers）
- Pages 访问量（仓库 Insights → Traffic）
- Issues 里的真实策略请求数（这是产品价值的直接证据）

## 免责声明一致性

任何对外内容都必须带免责声明。仓库里已经有四处：
README 顶部、面板顶部横幅、`report.json` 字段、`docs/DISCLAIMER.txt`。
新增内容时保持一致。
