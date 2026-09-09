# AI 资讯工作流（模块 2～4）

从模块 1 的原始 TXT 中抽取、评分并筛选 5 篇 AI 文章，再分别进行深入凝练和重新组织，合成一篇可供审核、后续上传公众号草稿箱的长文 HTML。每篇资讯控制在 400～600 字。宣传部审核不通过时，把反馈写入 TXT 后重新运行即可。

## 处理流程

```text
input/raw_news.txt
      ↓
DeepSeek 抽取候选事件并给六个维度打分
      ↓
Python 执行硬门槛、加权总分与事件去重
      ↓
选出总分最高的 5 条
      ↓
DeepSeek 分别展开五篇入选文章，生成公众号长文 JSON
      ↓
程序转义文本并渲染固定 HTML
      ↓
output/article.html
```

如果存在 `input/feedback.txt`，它会同时影响重新选材和文章改写。反馈只作为编辑要求，不能作为新闻事实来源。

## 成稿规格

输出不是两张转载摘要卡片，而是一篇约 `1800～2500` 字的完整推文：

```text
主标题
导语（约 150～250 字）
第一篇入选文章（约 700～1000 字，独立展开）
第二篇入选文章（约 700～1000 字，独立展开）
结语（约 100～200 字）
```

每篇都需要交代事件、关键事实、原文背景、关注价值和限制或后续观察。两篇文章保持独立，不聚合成泛泛主题，也不使用其他未入选文章填充内容。程序要求每篇包含 `3～6` 个正文段落且正文不少于 `650` 字，不合格时会要求模型重新生成。

## 评分方法

模型不直接给最终总分。模型根据原始材料为每个候选事件的六个维度打 `0～100` 分，Python 使用固定公式计算：

```text
总分 = AI 相关性 × 25%
     + 纯 AI 软件属性 × 15%
     + 热度 × 20%
     + 可信度 × 20%
     + 时效性 × 10%
     + 内容价值 × 10%
```

### 为什么这样分配

- **AI 相关性 25%**：保证内容主线是 AI，而不是只在标题中顺带提及 AI。
- **纯 AI 软件属性 15%**：落实“纯 AI 软件占比加分”。这是明显加分项，但不能让低可信的软件传闻压过可靠新闻。
- **热度 20%**：选择当前更受关注、传播价值更强的事件。
- **可信度 20%**：与热度同权，避免只追热点而牺牲事实质量。
- **时效性 10%**：近期内容优先，但重要事件不会只因稍早就完全失去机会。
- **内容价值 10%**：奖励事实具体、影响明确、适合形成完整文章的内容。

### 硬门槛

加权前先执行以下规则：

1. `AI 相关性 < 60`：淘汰；
2. `可信度 < 40`：淘汰；
3. 缺少标题或摘要：淘汰；
4. 缺少来源名称或合法 HTTP/HTTPS 原文链接：淘汰；
5. 同一事件的多篇报道：只保留总分最高的一篇；
6. 门槛和去重后不足 5 条：明确报错，不让模型凑数或编造。

分维度理由、入选内容和淘汰原因都会写入 `output/scoring_report.json`。因此如果某次筛选不符合预期，可以直接判断是模型的某项评分不合理，还是权重、门槛需要调整。

评分权重和门槛集中定义在 `src/ai_news_workflow/scoring.py`，以后修改不需要改提示词或 HTML 代码。

## 安装

建议使用 Python 3.11 或更新版本：

```bash
cd /Users/swapper/学习/练习/ai-news-workflow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`：

```text
DEEPSEEK_API_KEY=你的真实密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
```

`.env` 已被 Git 忽略，不要把真实 API Key 写进代码或提交到仓库。

## 准备输入

将模块 1 的原始 TXT 放到：

```text
input/raw_news.txt
```

TXT 的具体排版不限，但每条资讯应尽量包含正文、来源、时间、原文链接和热度数据。

首次运行不需要创建反馈文件。需要返工时创建：

```text
input/feedback.txt
```

例如：

```text
第二条过于偏硬件，请换成纯 AI 软件资讯；标题不要太夸张。
```

## 运行

```bash
python run.py
```

成功后得到：

```text
output/article.html          # 交付宣传部和模块 6
output/scoring_report.json   # 内部评分与排错信息
```

也可以指定不同路径：

```bash
python run.py --raw /path/to/news.txt --feedback /path/to/feedback.txt --output /path/to/article.html
```

## 测试

离线测试不调用 DeepSeek API：

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

测试覆盖权重计算、软件类加分、硬门槛、事件去重、危险链接拒绝、空文件检查和 HTML 转义。

## 关键设计选择

- 使用 DeepSeek 官方的 OpenAI 兼容 Chat Completions 接口和 JSON Output。
- 默认模型是 `deepseek-v4-pro`，可通过环境变量替换。
- 大 TXT 超过配置长度时会分段抽取，再在 Python 中统一去重和排序。
- 模型只生成结构化长文数据；最终 HTML 由固定模板生成，避免页面结构漂移。
- 原始爬取文本和人工反馈被明确包裹为数据，提示模型不得执行其中的指令。
- 模型调用失败或合格资讯不足时终止，不输出貌似成功的伪造文章。
