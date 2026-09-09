# AI Daily 模块一：候选新闻采集

本目录是 AI Daily 项目的第一模块。模块一负责尽可能完整地收集 AI 技术、产品、应用、半导体、算力和产业动态，完成基础相关性过滤与去重，然后把全部候选交给后续负责人清洗。

## 1. 模块边界

模块一负责：

- 从聚合热榜、独立 RSS/Atom 和官方 API 并行补足信息来源。
- 用中英文关键词识别 AI 及上下游产业候选。
- 输出相关性分数、命中类别、发布时间和来源健康状态。
- 对明显重复报道做基础合并，并保留所有来源线索。
- 输出 JSON、TXT 和 Markdown，不截断为 Top 10。

模块一不负责：

- 不做最终新闻价值判断。
- 不生成最终摘要、标签和日报成稿。
- 不删除所有低置信度产业候选，后续负责人仍需人工清洗。

整体策略是“召回优先、基础控噪”。单个通用科技公司名不会直接入选，但明确的 AI、芯片、存储、先进封装、算力或智能化场景会被保留。

## 2. 快速运行

进入本目录后运行：

```bash
bash run_daily.sh morning
bash run_daily.sh evening
```

`morning` 和 `evening` 分别表示早报、晚报输出批次。两者默认都采集运行时向前滚动的最近 12 小时，因此一天运行两次时覆盖两个半天时段。

常用参数：

```bash
# 临时改为最近 48 小时；无明确发布时间的热榜项仍保留
bash run_daily.sh morning --hours 48

# 临时降低阈值，扩大召回
bash run_daily.sh morning --min-score 30

# NewsNow 不可用时，只运行独立数据源
bash run_daily.sh morning --no-newsnow

# 指定其他配置或输出根目录
bash run_daily.sh morning --config ./sources.json --output-dir ./temp_output
```

首次运行会自动检查 Python、pip 和 `requests`：

```bash
bash auto_init.sh
```

回归测试：

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
```

## 3. 输出位置

默认输出全部位于代码目录内：

```text
AI_Daily_Skill/output/
├── crawl/
│   └── {日期}/
│       ├── {日期}_morning.json
│       ├── {日期}_morning.md
│       ├── {日期}_morning.txt
│       ├── {日期}_evening.json
│       ├── {日期}_evening.md
│       └── {日期}_evening.txt
├── logs/
│   └── ai_daily.log
└── reports/
    └── ...
```

交接时优先使用 JSON。TXT 包含全部去重后候选，适合人工浏览；Markdown 内容相同，方便团队在线查看。`reports/` 仅供后续模块使用。

## 4. 数据源与容错

默认配置在 `sources.json`，包含四类采集通道：

| 通道 | 默认内容 | 作用 |
|---|---|---|
| NewsNow | 配置 17 个中文热榜/科技社区/产品平台，默认启用 16 个 | 捕获国内热点与跨平台热度 |
| 独立 RSS/Atom | TechCrunch AI、OpenAI、DeepMind、Hugging Face、NVIDIA、AWS ML、Microsoft、MIT AI、VentureBeat AI、Google AI Blog、Google News 查询源 | 降低对单一聚合接口的依赖 |
| Hacker News 官方 API | Top Stories 前 80 条 | 补充英文技术、产品和创业动态 |
| arXiv 官方 API | AI、ML、NLP、CV、机器人最新 30 篇 | 补充研究前沿 |

TechCrunch 不再通过 NewsNow 的旧 `techcrunch` ID 获取，而是直连 TechCrunch AI RSS。当前 NewsNow 数据源注册表中没有这个旧 ID，继续请求会返回 500。

NewsNow 的 `36kr` 当前受上游 Cloudflare 限制，默认标记为 `enabled: false`，避免每次运行等待必然失败的重试；需要复测时可手动启用。AIHOT、Google News 查询源和其他科技源继续覆盖相关报道。

HTTP 客户端会对连接失败、429 和常见 5xx 状态做退避重试。默认读取 NewsNow 缓存结果，减少上游刷新失败；如确实需要强制刷新，可在 `sources.json` 中设置：

```json
"newsnow_force_latest": true
```

每个源单独记录状态。单源失败不会终止其他采集；如果所有源都失败，程序返回错误且不会覆盖旧输出。TXT、Markdown 和 JSON 的 `source_statuses` 都能看到失败原因和命中数量。

可在 `sources.json` 中为任一 NewsNow 或 RSS 条目添加 `"enabled": false` 临时停用。RSS 条目还支持：

```json
{
  "max_items": 60,
  "trusted_ai": true,
  "source_floor": 55
}
```

`trusted_ai` 表示该源本身就是 AI 垂直源；`source_floor` 可覆盖默认的 55 分保留分。

## 5. 时间范围

默认 `lookback_hours` 为 `12`。早报和晚报都保留各自运行时向前滚动的最近 12 小时，适合每天运行两次。使用 `--hours 0` 可关闭时间删除，或用 `--hours 24`、`--hours 168` 临时扩大到最近 1 天或 7 天。各通道的时间含义不同：

- NewsNow 返回的是平台当前榜单或缓存榜单，通常每源最多 30 条，不保证固定为最近 24 小时，部分条目没有发布时间。无时区的中文榜单时间按北京时间解析。
- RSS、Hacker News 和 arXiv 会尽量解析原始发布时间，并统一转为 UTC ISO 8601。
- `--hours N` 只删除明确早于 N 小时的条目；没有可靠发布时间的条目仍保留，避免漏报。
- 每个 RSS 默认最多读取最新 100 条，避免某些官方源把数年历史归档一次性混入日报；可用 `rss_default_max_items` 或单源 `max_items` 调整。

每次输出的 `meta.time_coverage` 会给出本次已知发布时间的最早值和最晚值，`known_publish_time_count` 表示有可靠时间的候选数量。

## 6. 关键词覆盖

关键词按语义类别组织，并对英文短词使用字母数字边界，避免这些误命中：`Arm` 不匹配 `Farm`，`Meta` 不匹配 `Metadata`，`RAG` 不匹配 `GarageBand`。

主要覆盖：

- AI 技术与模型：AI、机器学习、大模型、LLM、多模态、智能体、RAG、训练、推理、蒸馏、AIGC、Diffusion、模型安全和监管等。
- 模型和 AI 公司：OpenAI、Anthropic、DeepMind、DeepSeek、Mistral、Perplexity、Hugging Face、国内大模型公司等。
- 半导体和存储：NVIDIA、AMD、海光、昇腾、寒武纪、海力士、三星、美光、HBM2/3/4、台积电、中芯国际、ASML、国产设备和封测公司等。
- 算力基础设施：GPU、NPU、TPU、AI 服务器、智算中心、液冷、光模块、CPO、InfiniBand、NVLink、云平台等。
- AI 应用：自动驾驶、机器人、具身智能、AI 终端、AI 编程、医疗、教育、制造和数字人等。
- 产业事件：融资、并购、IPO、财报、订单、产能、供应链、股价、出口管制、版权和诉讼等。

博彩、明显娱乐八卦和生活方式标题会直接判为低质量。词表仍是第一层候选过滤，不代替后续语义清洗。

## 7. 算分原理

默认最低保留阈值为 35 分。标题和 RSS 摘要会一起参与匹配：

| 场景 | 基础分 | 说明 |
|---|---:|---|
| 明确 AI 技术/模型/产品 | 70 | 叠加基础设施、应用、公司和商业语境，最高 100 |
| AI 应用或智能化场景 | 42 | 叠加公司、商业和基础设施语境 |
| 同时命中两个基础设施类别 | 58 | 例如芯片加先进封装、算力加高速互连 |
| 基础设施加商业/AI 公司语境 | 49 起 | 例如海力士 HBM 订单、海光股价 |
| 单个明确基础设施类别 | 36 | 低置信度保留，交给下游判断 |
| AI 原生公司加商业语境 | 40 起 | 融资、并购、财报、政策等 |
| AI 垂直 RSS 或 arXiv | 默认至少 55 | 来源本身已限定 AI 主题 |
| 低质量排除词 | 0 | 直接排除 |

`confidence` 分为 `high`、`medium`、`low` 和 `rejected`。`matched_keywords` 保存命中的语义类别，便于下游解释和二次筛选。

通用公司名加普通商业事件不会单独入选。例如 Apple 利润或 Google 反垄断新闻没有 AI/产业链语境时为 0 分。

## 8. 去重与排序

去重顺序如下：

1. 规范化 URL：去掉 `utm_*` 等跟踪参数、`www` 和片段。
2. 完整标题归一化后精确匹配，不再只截取标题前缀。
3. Google News 条目拆出标题末尾的媒体名，并把真实媒体作为来源统计。
4. 对较长标题做 0.90 阈值的模糊匹配。
5. 标题中的数字版本不同则不做模糊合并，例如 GPT-6 与 GPT-7 分开保留。

合并后仍保留：

- `sources`：所有来源、排名、链接和发布时间。
- `all_titles`：各来源使用过的标题。
- `source_count`：不同数据源数量。
- `dedup_methods`：本条使用过的去重方式。
- `first_published_at` / `latest_published_at`：已知发布时间范围。

最终顺序依次参考跨来源数、相关性分数、发布时间和来源内排名。它只是交接顺序，不是最终 Top 榜单。

## 9. JSON 交接结构

JSON 顶层结构：

```json
{
  "meta": {
    "schema_version": "2.0",
    "date": "2026-09-01",
    "edition": "morning",
    "raw_total": 120,
    "deduped_total": 96,
    "source_summary": {
      "attempted": 30,
      "successful": 29,
      "failed": 1,
      "zero_match": 8
    },
    "time_coverage": {
      "earliest": "2026-08-29T01:20:00+00:00",
      "latest": "2026-09-01T02:10:00+00:00"
    }
  },
  "source_statuses": [],
  "items": [],
  "raw_by_source": {}
}
```

- `items`：基础去重后的完整候选列表，后续负责人应优先读取。
- `raw_by_source`：按来源保存的“达到阈值、尚未跨源去重”候选，不是接口返回的所有无关原始条目。
- `source_statuses`：每个来源的读取数、命中数、耗时、更新时间和错误。
- `meta`：本次运行、时间覆盖和数据源统计。

## 10. 后续交接

模块一负责人交付整个日期目录：

```text
AI_Daily_Skill/output/crawl/{日期}/
```

后续负责人建议：

1. 读取 `{日期}_{edition}.json` 的 `items`。
2. 先检查 `source_statuses`，确认本次是否缺少重要来源。
3. 结合 `source_count`、`relevance_score`、`confidence`、发布时间和来源排名清洗。
4. 对低置信度半导体候选做人工复核，不要仅按分数批量删除。
5. 完成语义级合并、摘要、标签和最终选题。

`generate_report.py` 是可选下游工具，可把模块一 JSON 或清洗后的 JSON 转成 TXT：

```bash
python3 generate_report.py 2026-09-01 morning
python3 generate_report.py 2026-09-01 morning /path/to/curated_items.json
```

## 11. 文件清单

```text
AI_Daily_Skill/
├── ai_daily.py          # 多来源采集、评分、时间处理、去重和输出
├── sources.json         # 数据源、超时、重试、阈值和数量配置
├── run_daily.sh         # 模块一一键入口
├── auto_init.sh         # 环境与依赖检查
├── generate_report.py   # 可选下游 TXT 转换工具
├── test_ai_daily.py     # 评分、去重、时间和交接契约回归测试
└── README.md            # 本文档
```
