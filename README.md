# AI Daily 新闻工作流

**本项目由香港中文大学（深圳）AI 协会技术部成员们共同完成。**

抓取 AI 资讯 → AI 清洗成稿 → docx + 图片附件 → 人工审核 → 一键进公众号草稿箱。

## 运行逻辑（一图流）

```
menu.bat [1] 或 每日自动(到 09:00)
      │
      ▼
① 爬虫 crawler（30 个数据源，实时进度条 0→100%）
      │  items.json（去重后候选）
      ▼
② AI 清洗与成稿 summarize（本地模型 或 DeepSeek）
      │  评分 → 选 5 篇 → 每篇 400～600 字 → article_source.html + scoring_report.json
      ▼
③ 为入选 5 篇抓配图（自动排除视觉重复图；文字总结只看正文）
      ▼
④ 生成审核产物 review/{日期}(-v1/-v2…)/
      │   新闻稿_{日期}.docx / article.html / cover.jpg / attachments/
      │   （同一天重复生成自动存 -v1、-v2…，绝不覆盖旧版）
      ▼
人工审核（模块 5）
   ├─ 不通过 → feedback.txt → 重按 [1] 出新版（旧版保留）
   └─ 通过 → menu.bat [3] → 本机 Chrome 网页上传 → 公众号草稿箱（人工预览发布）
```

自动生成只做 ①~④（把稿子放 review/ 等人审），**推送永远等人工审核后手动触发**。

## 目录
```
AI-Daily-Workflow/
├─ menu.bat             ★ 唯一日常入口（数字菜单）
├─ setup.bat            首次安装（建 .venv、装依赖）
├─ requirements.txt / .env(.example)
├─ app/                 胶水层：config  state  convert  images  docx_builder
│                        html_wechat  orchestrator(进度/编排)  scheduler  control(CLI)
├─ modules/
│  ├─ crawler/          模块1 采集（30 数据源）
│  ├─ summarize/        模块2~4 清洗/评分/成稿
│  └─ wechat/           模块6 推公众号草稿箱
├─ review/{日期}(-v1/-v2…)  ★ 审核文件夹（docx + 图片附件 + html + 封面；同日多版本并存）
├─ data/                运行时数据；wechat-cover/cover.jpg 是公众号固定封面
├─ docs/ARCHITECTURE.md 模块接口协议（文件/命令/退出码）
├─ tests/               离线单测
└─ README.md
```

## 与 menu.bat 等价的底层命令（CLI）
```powershell
python app\control.py today [--sample] [--feedback 文件]   # 开始今日生成
python app\control.py push                                 # 列出 review 内 HTML，输入编号上传；0 取消
python app\control.py push --file review\2026-09-09-v2\article.html  # 指定某份已审核的 HTML
python app\control.py push --date YYYY-MM-DD                # 精确指定子目录中的 article.html
python app\control.py auto on|off [--time 08:30]            # 自动开关
python app\control.py serve                                 # 常驻调度
python app\control.py status                                # 状态
```

## 配置（.env，由 .env.example 复制）
菜单 [3] 会先显示稿件路径、标题和修改时间。实际上传所选 HTML 及同目录正文图片；Word 是审核副本，修改 Word 不会自动同步到 HTML。不同版本可分别选择。

上传使用项目专用的本机 Chrome 登录公众号后台，直接在网页编辑器中填写标题、正文、图片、摘要和封面并保存草稿。它不调用公众号开放 API，因此校园网、手机热点和动态公网 IP 都不需要加入 IP 白名单。首次使用或微信登录过期时扫码一次，登录状态保存在 `data/wechat-browser-profile/`（已排除版本控制）。

公众号封面固定读取 `data/wechat-cover/cover.jpg`。仓库不包含个人封面；首次安装按下文创建占位图，确定正式封面后直接用新图片覆盖该文件，文件名保持 `cover.jpg`，后续所有上传都会自动使用它。

| 变量 | 说明 |
|---|---|
| WECHAT_APP_ID / WECHAT_APP_SECRET | 仅旧 API 上传模块使用；菜单 [3] 网页上传不需要 |
| DEEPSEEK_API_KEY/BASE_URL/MODEL | 填了用 DeepSeek；不填自动用本地模型 |
| LLM_LOCAL_BASE_URL/LLM_LOCAL_MODEL | 本地 OpenAI 兼容服务（Qwen，127.0.0.1:8080） |
| SCHEDULE_TIME / AUTO_ENABLED | 每日自动时间与开关 |
| ARTICLE_TITLE | 可选：覆盖推送标题（默认简短“AI 每日资讯 日期”） |

## 设计与纪律
- 模块间零 import，全部「子进程 + 文件 + 退出码」对接（便于替换/升级/接 Gamma）。
- 失败即中断，绝不拿旧文件继续推送；每次运行写 data/runs/*.json。
- 终端实时：爬虫百分比进度条、成稿心跳、各阶段耗时。
- 本地 llama.cpp 和 DeepSeek 默认都启用 JSON 输出约束；成稿显示抽取进度和具体重试原因，输出被 token 上限截断时会明确报错。
- 生成开始记录 `running`，失败记录 `failed` 及错误清单；最近一次生成失败或尚未完成的日期不能推送。
- 测试：`python -m unittest discover -s tests -v`（离线）。

## 从零开始使用

### 1. 安装

准备 Windows、Python 3.10+、Git 和 Google Chrome。联网抓取与网页上传需要正常网络。

```powershell
git clone https://github.com/Lby1102/AI_Daily.git
cd AI_Daily
.\setup.bat
```

安装脚本创建 `.venv`、安装 `requirements.txt`，并在 `.env` 不存在时从 `.env.example` 复制配置。不会覆盖已有 `.env`。主工作流只需填写仓库根目录 `.env`；模块内的模板仅供独立运行相应模块使用。

### 2. 选择成稿引擎并手动填写配置

以下两种方式任选一种。实际密钥只写入本机 `.env`，不要填入 `.env.example`。

**使用 DeepSeek API**：手动申请自己的 API Key，将根目录 `.env` 中 `LLM_PROVIDER` 设为 `deepseek`，填写 `DEEPSEEK_API_KEY`。核对 `DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL` 是否适用于自己的服务账号；调用费用由该账号承担。

**使用本地模型**：将 `LLM_PROVIDER` 设为 `local`，配置 `LLM_LOCAL_BASE_URL`、`LLM_LOCAL_MODEL` 和服务要求的 `LLM_LOCAL_API_KEY`。默认地址是 `http://127.0.0.1:8080/v1`，模型别名是 `qwen3.5-9b`，无鉴权本地服务的 Key 可保持 `local`。

仓库不包含模型权重、llama.cpp 引擎或其运行库，也不会自动下载。需要自行准备兼容的 OpenAI 接口服务；如使用项目自动启动功能，目录结构为：

```text
仓库的上级目录/
├─ AI_Daily/
└─ llm/
   ├─ engine/llama-server.exe  （以及引擎所需运行库）
   └─ models/Qwen3.5-9B-Q4_K_M.gguf
```

自定义位置时，在 `.env` 增加 `LLM_DIR=C:/你的目录/llm`，并设置 `LLM_MODEL_FILE`。模型和引擎必须匹配，机器内存/显存应满足模型要求。自动启动默认使用 16384 上下文；自建服务需留足输入和输出空间。

`LLM_PROVIDER=auto` 表示有 DeepSeek Key 就使用 DeepSeek，否则使用本地服务。下载代码本身不会让本地模型自动就绪。

| 需要手动准备的信息 | 何时需要 |
|---|---|
| DeepSeek API Key、服务地址、模型名 | 选择云端成稿时 |
| 本地模型、引擎、服务地址、模型别名和可选鉴权 Key | 选择本地成稿时 |
| 微信管理员/运营者扫码登录 | 首次上传或登录过期时 |
| 固定封面 `data/wechat-cover/cover.jpg` | 上传草稿前 |
| `ARTICLE_AUTHOR`、可选摘要等 | 希望自定义作者或摘要时 |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 仅独立运行旧 API 上传模块时；菜单 [3] 不需要 |

### 3. 准备固定封面

可以先用仓库提供的通用图片占位，在仓库根目录执行：

```powershell
New-Item -ItemType Directory -Force data/wechat-cover
Copy-Item app/assets/default-news.jpg data/wechat-cover/cover.jpg
```

这条复制命令会覆盖同名封面；已有正式封面时不要再执行。之后换图只需替换 `cover.jpg`，无需修改代码。

### 4. 生成、审核、上传

双击 `menu.bat`：

| 菜单 | 操作 |
|---|---|
| [1] | 抓取资讯、筛选 5 条、逐篇生成 400–600 字，再拼接导语/结语并生成 HTML、Word 和图片 |
| [2] | 打开审核文件夹，查看最新成稿 |
| [3] | 列出 review 中的 HTML，按编号选择并保存到公众号草稿箱 |
| [4] | 开启每日定时生成，并保持调度进程运行 |
| [5] | 关闭每日自动生成 |
| [6] | 查看状态与最近生成结果 |
| [0] | 退出菜单 |

同日再次生成会创建更高的 `-vN` 版本，保留旧稿。每篇长度不达标会单独重试，默认最多 8 次重试（共 9 次尝试）；耗尽后仍会明确报错，不上传残缺稿件。

审核时核对事实、来源、文字和配图。实际上传的是 `article.html`，修改 Word **不会**同步修改 HTML。需要修改上传内容时编辑相应 HTML，或使用 CLI 的 `--feedback` 提供修改意见重新生成。

选 [3] 后，在项目专用 Chrome 窗口扫码登录目标公众号。程序填写内容并保存草稿；在公众号后台的草稿箱再次检查排版和图片，发布由运营者手动完成。登录会过期，微信页面变化也可能需要调整自动化代码。

### 5. 每日自动运行

默认每天 09:00；可在 `.env` 修改 `SCHEDULE_TIME`，或使用：

```powershell
.\.venv\Scripts\python.exe app/control.py auto on --time 09:00
.\.venv\Scripts\python.exe app/control.py serve
```

当前实现是 **Python 常驻调度进程**，不自动注册 Windows 任务计划。电脑需保持开机、联网且不休眠，调度进程需保持运行；重启电脑后需重新启动。自动任务只生成待审核稿件，不自动发布。

### 6. 常见问题

- **找不到本地模型**：检查上述引擎与权重路径，或先启动自己的本地服务，再核对 `.env` 地址。
- **API 鉴权失败**：核对当前引擎及 Key；不要把包含密钥的配置或请求头贴到公开 Issue。
- **成稿耗时较长**：终端会输出抓取进度、逐篇生成和校验重试信息，本地耗时取决于硬件与模型。
- **没有固定封面**：按第 3 步创建 `cover.jpg`。
- **上传需要扫码/页面操作失败**：在弹出的 Chrome 登录，确认使用正确公众号，然后重试；查看本地日志定位失败步骤。
- **微信 40164 / IP 白名单报错**：该错误属于旧 API 上传模块。菜单 [3] 采用网页上传，不需要配置 IP 白名单。

## 隐私与提交规则

`.gitignore` 排除本机 `.env`、密钥文件、浏览器登录资料/Cookie、运行数据、日志、审核成稿、个人封面、模型权重和虚拟环境。公开仓库只保存空白配置模板、源码、测试及通用静态资源。Git 忽略规则不是加密，也无法撤回已提交的秘密；不要使用 `git add -f` 强行添加这些文件。若密钥曾泄露，应在服务后台撤销并重新生成。

提交前可执行 `git status --short` 和 `git diff --cached` 检查文件与内容。不要把私人资料写进测试、README 或模板。
