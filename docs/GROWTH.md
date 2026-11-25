# 增长手册 / Growth playbook

拿 100 star 的实际路径，按性价比排序。

## 前提：star 的两个来源

1. **被搜到**（SEO / GitHub Explore / topic 标签）—— 需要有人搜"backtesting"、"资产配置"、"A股"
2. **被推**（社交分享 / Hacker News / 掘金 / V2EX / 即刻）—— 需要有人读完觉得值得转

代码质量决定下限，**曝光**决定上限。

## 当前状态（2026-11-26）

- Star：**0**（目标 100）
- 仓库：https://github.com/aazh2026/vlab
- 在线演示：https://postcodeengineering.com/vlab/（GitHub Pages，源目录 `main /docs`）
- 测试：52 个，CI 覆盖 Python 3.9–3.12，全绿
- Release：v1.0.0 已发布
- Discussion #1 已开（"你的配置我来回测"征集帖）

## 已完成

### 基础设施

- [x] 中英双语 README，含真实数字表格
- [x] 在线演示（GitHub Pages，自定义域名 + 证书已批准）
- [x] 零依赖 + 零 CDN 徽章（CI 用 `--no-index` 安装验证）
- [x] CI 多 Python 版本绿灯 + 打包 job
- [x] Issue 模板（bug / 策略请求）+ Discussions 开启
- [x] 社交预览图（SVG 精确排版 + headless Chrome，1280×640）
- [x] **README 顶部 18 秒 demo 动图**（CDP 驱动真实面板抓帧，WebP 405 KB）
- [x] `docs/POST_zh.md` —— 可直接发布的中文长文草稿
- [x] CONTRIBUTING 里写清"怎么加自己的策略"

### 收录 PR（已提交，等待维护者合并）

| 仓库 | Star | PR | 状态 |
|---|---|---|---|
| wilsonfreitas/awesome-quant | 30.9k | [#1081](https://github.com/wilsonfreitas/awesome-quant/pull/1081) | OPEN CLEAN，CI 全绿 |
| thuquant/awesome-quant | 5.7k | [#131](https://github.com/thuquant/awesome-quant/pull/131) | OPEN CLEAN |
| jobbole/awesome-python-cn | 30.7k | [#150](https://github.com/jobbole/awesome-python-cn/pull/150) | OPEN CLEAN |
| AI4Finance-Foundation/Awesome_AI4Finance | 340 | [#72](https://github.com/AI4Finance-Foundation/Awesome_AI4Finance/pull/72) | OPEN CLEAN |
| georgezouq/awesome-ai-in-finance | 6.8k | [#402](https://github.com/georgezouq/awesome-ai-in-finance/pull/402) | OPEN CLEAN |

### 已评估但**未**提交（及原因）

- **vinta/awesome-python**（337k）—— 要求"仓库至少 1 个月"且"仅列 obvious choices"，
  收录标准以 PyPI 下载量为主。仓库太新、PyPI 还没上架，提交大概率被拒。
  **前置条件：先发 PyPI。**
- **moov-io/awesome-fintech** —— 其 `AGENTS.md` 明确写明拒收回测/交易/行情类项目。
- **grananqvist/Awesome-Quant-Machine-Learning-Trading**（4.2k）—— 定位是 ML 量化，
  vlab 不做 ML，条目会显得不搭。
- **0voice/Awesome-QuantDev-Learn**（1.2k）—— 是学习路线图，不是工具收录列表。

## 优先级清单

### P0 —— 需要 Aaron 凭据

1. **发布到 PyPI**
   这是 `vinta/awesome-python` 的硬门槛，也是最独立的外部曝光源。
   需要的：一个 PyPI API token（Account → API tokens → scope: project `vlab`）。
   包已构建好（wheel + sdist，`dependencies = []`），CI 已校验可安装。
   > token 不要发在聊天里。

2. **发布中文长文**
   渠道：V2EX（技术）、掘金（技术）、知乎（想法）、即刻（投资/独立开发）、少数派。
   草稿：`docs/POST_zh.md`。V2EX 有 Cloudflare 反自动化，需要真实登录态的浏览器。
   标题建议：
   - 「我写了个资产配置回测框架，然后发现它骗了我」
   - 「回测里那 5 个 bug，每一个都足以让结论完全反转」
   - 「为什么我不再相信没有测试的量化回测」

   贴 GitHub 仓库 + Pages 演示链接。**不要**贴收益承诺。

### P1 —— 一到两周

3. **Reddit**：r/algotrading、r/Python、r/fintech。
   标题偏技术、不荐股，社区对"投资建议"极其敏感。
   r/algotrading 允许自推广，其余需先有评论互动。

4. **Hacker News**：`Show HN: vlab – zero-dependency portfolio backtesting lab with regression tests for its own historical bugs`
   建议时间：太平洋时间上午（美东工作时段），点击量只有 5 分钟窗口。

5. **英文 README 单独优化**：面向英文社区，删掉个人叙事，突出 API 和可复用性。

### P2 —— 持续

6. **「你的配置我来回测」活动**（Discussion #1 已开）。
   价值不是 star，是**真实使用案例和 Issue**，而真实案例是最好的 star 磁铁。

7. **中文量化社区**：vnpy / QUANTAXIS / Hikyuu 的 issue 里提"要不要加一个回测基准"。
   风险低、曝光准，但要写得像"发现了你们一个可以互相验证的东西"，不要像广告。

## 不要做的事

- ❌ 不要在标题/简介里承诺收益
- ❌ 不要发"推荐买入"式内容 —— 会招黑粉，且违背项目自己的免责声明
- ❌ 不要买 star。项目价值建立在"诚实的回测"上，买 star 会摧毁这个立意
- ❌ 不要为了 star 加一堆无用功能。**少而准 > 多而杂**

## 度量

- Weekly stars（`gh api repos/aazh2026/vlab` 的 `stargazers_count`）
- 五个收录 PR 的合并状态（合并后才是真正的曝光）
- Pages 访问量（仓库 Insights → Traffic）
- Discussions #1 里的真实策略请求数（产品价值的直接证据）

## 免责声明一致性

任何对外内容都必须带免责声明。仓库里已经有四处：
README 顶部、面板顶部横幅、`report.json` 字段、`docs/DISCLAIMER.txt`。
新增内容时保持一致。

## 踩过的坑（别再踩）

- **Pages 发布目录是 `main /docs`**，不是 `site/`。`scripts/build_site.py` 现在会
  同步到 `docs/`，改构建脚本时别把这个同步删了。
- **无头浏览器抓帧用 CDP 而非录屏工具**：Node 26 自带 WebSocket，
  `Target.createTarget` → `captureScreenshot` → ffmpeg/Pillow 合成，零依赖。
- **动画 WebP 比 GIF 小一个数量级**（405 KB vs 1.2 MB），GitHub README 支持。
  用 Pillow 的 `save_all` + 每帧 duration（真实时间戳，不是固定值）。
- **awesome 列表几乎都要 fork + PR**，直接 push 会被拒（403）。
- **zsh 不做默认单词分割**：`for x in a b; do echo $1` 里的 `$1` 是空的，
  循环内拆参数要用 `w="${cfg%%:*}"` 这种写法。
