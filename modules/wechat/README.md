# AI Daily：HTML 推送到微信公众号草稿箱

本项目把本地 HTML 文章及其图片上传到微信公众号，并在公众号后台创建一篇
草稿。程序只负责创建草稿，**不会自动群发**；公众号管理员仍需预览、修改并
决定是否发布。

## 项目结构

```text
AI协会项目/
├─ content/
│  ├─ article.html       要上传的文章正文
│  └─ test.png           当前测试封面
├─ wechat_draft_pusher/  推送程序
├─ main.py               命令行入口
├─ requirements.txt      Python 依赖
└─ .env.example          配置示例，不包含真实密钥
```

## `content/article.html` 有什么用

`content/article.html` 是公众号草稿的**文章来源**。执行推送时，程序会：

1. 读取 HTML 的文章标题和 `<body>` 正文。
2. 找到正文中的 `<img>` 图片并上传到微信。
3. 把本地图片地址替换为微信返回的图片地址。
4. 使用 `test.png` 作为封面。
5. 调用微信草稿箱接口创建草稿。

默认标题读取顺序如下：

1. 环境变量 `ARTICLE_TITLE`
2. `<meta name="wechat:title" content="文章标题">`
3. `<title>文章标题</title>`
4. 正文中的第一个 `<h1>`

最简单的文章示例：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <title>本周 AI 资讯</title>
  </head>
  <body>
    <section style="font-size: 16px; line-height: 1.8; color: #333;">
      <h1>本周 AI 资讯</h1>
      <p>这里填写文章正文。</p>
      <img src="./news-image.png" alt="资讯配图">
    </section>
  </body>
</html>
```

如果使用 `src="./news-image.png"`，请把图片放在 `content/news-image.png`。
支持相对路径、绝对路径、HTTP(S) 地址和 base64 图片。CSS 背景图不会自动
上传，正文配图应使用 `<img>`。

每次推送前，请先修改并保存 `content/article.html`。程序不会自动从 Word、
微信公众号编辑器或其他网页中获取内容。

## 首次安装

需要 Python 3.10 或更高版本。在项目目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

项目使用以下 Windows 环境变量：

```text
WECHAT_APP_ID
WECHAT_APP_SECRET
```

不要把真实凭据写入代码、README、`.env.example` 或提交到 GitHub。
`AppSecret` 应视为公众号密码。

## 手动上传到草稿箱

这里的“手动上传”是指由你主动执行一次命令，不等待定时任务。

1. 修改 `content/article.html`。
2. 确认封面文件为 `content/test.png`。
3. 在 PowerShell 中进入项目目录：

```powershell
cd C:\Users\china\Desktop\AI_Daily_Github\AI协会项目
```

4. 检查文件、凭据和定时配置：

```powershell
.\.venv\Scripts\python.exe main.py check
```

5. 创建公众号草稿：

```powershell
.\.venv\Scripts\python.exe main.py push
```

看到“草稿创建成功”后，公众号管理员可以登录
[微信公众平台](https://mp.weixin.qq.com/)，在草稿箱中查看、预览和编辑。
这一步不会向关注者发送消息。

如果管理员删除了后台封面素材，或需要强制重新上传封面：

```powershell
.\.venv\Scripts\python.exe main.py push --refresh-cover
```

每执行一次 `push` 都会新增一篇草稿。测试时请避免连续重复执行。

## 更换文章或封面

更换文章：

- 直接编辑 `content/article.html`；或
- 设置 `ARTICLE_HTML`，指向另一个 HTML 文件。

更换封面：

- 替换 `content/test.png`；或
- 设置 `COVER_IMAGE`，例如 `content/cover.jpg`。

封面支持 JPG 和 PNG。更换文件内容后，程序会根据文件哈希上传新素材。

## 定时推送

常驻调度命令：

```powershell
.\.venv\Scripts\python.exe main.py schedule
```

默认 cron 为每周一 09:00，时区为 `Asia/Shanghai`。可通过环境变量修改：

```text
PUSH_CRON=0 9 * * 1
TIMEZONE=Asia/Shanghai
```

cron 格式为 `分 时 日 月 周`：

```text
0 9 * * 1      每周一 09:00
30 18 * * 5    每周五 18:30
0 10 1 * *     每月 1 日 10:00
```

运行 `schedule` 后，PowerShell 窗口和电脑都必须保持运行。长期使用更推荐
Windows 任务计划程序定时执行 `main.py push`。

## 本地测试

本地测试不会调用微信接口：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 常见问题

- `40164`：当前出口公网 IP 不在公众号接口白名单。
- `40013`：`AppID` 不正确。
- `40125`：`AppSecret` 不正确。
- `48001`：公众号没有素材或草稿箱接口权限。
- `40007`：缓存的封面素材已被删除，使用 `--refresh-cover`。
- 环境变量缺失：重启 PowerShell 或 Codex，使新变量进入当前进程。
- 排版与浏览器不同：微信会过滤部分 HTML/CSS，请让管理员在发布前预览。

## 安全说明

- 不要提交包含真实凭据的 `.env`。
- 不要在聊天、截图、日志或群文件中暴露 `AppSecret`。
- 运行机器的公网 IP 必须加入公众号接口 IP 白名单。
- 若怀疑密钥泄露，应立即在公众号后台重置 `AppSecret`。
