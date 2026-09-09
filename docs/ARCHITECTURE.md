# 模块接口协议（API 约定）

本工作流把三个独立交付模块原样保留在 `modules/`，统一由 `app/orchestrator.py`
以 **子进程 + 文件契约** 方式串联。任何模块失败都表现为退出码/异常，不会污染下游。

## 目录
```
AI-Daily-Workflow/            ← 代码文件夹（下载整个目录即可运行）
├─ app/                       胶水层（编排/转换/docx/图片/调度/入口）
├─ modules/
│  ├─ crawler/                模块 1（原样 vendor）
│  ├─ summarize/              模块 2~4（原样 vendor）
│  └─ wechat/                 模块 6（原样 vendor）
├─ data/
│  ├─ crawl/{日期}/…          爬虫输出
│  ├─ work/{日期}/…           当次中间文件（raw txt / scoring / 原始 html）
│  ├─ runs/{时间戳}.json       每次运行清单
│  └─ state.json              自动开关等状态
├─ review/{日期}/             ★ 审核文件夹（给宣传部）
│  ├─ 新闻稿_{日期}.docx
│  ├─ article.html            公众号用（含图片、meta 标题、封面引用）
│  ├─ cover.jpg
│  └─ attachments/NN-主题/*.jpg
├─ logs/
├─ requirements.txt / .env(.example)
└─ README.md
```

## 模块 1（crawler）契约
- 命令：`python modules/crawler/ai_daily.py {morning|evening} --hours N --min-score M --output-dir <data/crawl>`
- 输入：无。输出：`data/crawl/{YYYY-MM-DD}/{YYYY-MM-DD}_{edition}.json`（取 `items[]`）
- 退出码：0 成功；非 0 = 失败（不写文件）。
- 关键字段：`title, snippet, url, sources[], source_count, best_rank, latest_published_at, relevance_score, confidence, matched_keywords`
- 约定：不含图片/正文全文；图片由选文后 `app/images.py` 单独抓取。

## 模块 2~4（summarize）契约
- 命令：`python modules/summarize/run.py --raw <raw.txt> --feedback <feedback?> --output <source.html> --report <scoring.json>`
- 输入：任意排版 TXT（整文交模型理解）；`feedback.txt` 存在即有内容则按反馈重做。
- 输出：`article.html`（标题/导语/2 篇/结语）+ `scoring_report.json`（`selected[]` 含候选原文 dict）。
- 退出码：0 = 生成成功；1 = 失败（文件缺失/API 失败/合格不足 2 条等）。
- LLM 配置来自环境变量：`DEEPSEEK_API_KEY/BASE_URL/MODEL`，扩展开关
  `DEEPSEEK_JSON_MODE`（默认开）、`DEEPSEEK_SEND_THINKING`（默认开）、`DEEPSEEK_MAX_RETRIES`。

## 模块 6（wechat）契约
- 命令：`python modules/wechat/main.py check|push [--refresh-cover]`
- 输入：`ARTICLE_HTML`（html 路径）、`COVER_IMAGE`（jpg/png）；正文 `<img>` 相对路径按 HTML 所在目录解析。
- 输出：微信草稿（每 push 一次新增一篇草稿）；退出码 0 成功 / 1 失败。
- 凭据：`WECHAT_APP_ID / WECHAT_APP_SECRET`（.env，勿提交）。公众号后台需加本机公网 IP 白名单。

## review/ 语义（人工审核）
1. 每天生成后产物落 `review/{日期}/`，审核人打开 **docx** 阅读，图片见 `attachments/`。
2. 不通过：把意见写入 `data/work/{日期}/feedback.txt`（或界面上提交）后重新生成，覆盖当日产物。
3. 通过：执行 `python app/control.py push` → 模块 6 把当日 `article.html`+封面推送到草稿箱。
   `review/{日期}/article.html` 是模块 6 唯一数据源（含 `<meta wechat:title>` 与本地图片）。

## 一致性原则
- 上游写完文件才启动下游（子进程顺序执行）；失败时不读旧文件继续推送。
- 模块各自独立，可单独升级/替换，胶水层不 import 模块内部实现。
