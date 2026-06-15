# HTML 定时推送到微信公众号草稿箱

这个项目读取一个 HTML 文件，上传正文图片和封面，然后调用微信公众号
草稿箱接口。它只创建草稿，不会自动群发。

## 1. 准备环境

需要 Python 3.10 或更高版本：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

把封面图片放到 `content/cover.jpg`，编辑 `content/article.html`，再填写
`.env` 中的公众号信息。

## 2. 检查与运行

```powershell
python main.py check
python main.py push
```

成功后，文章会出现在公众号后台的草稿箱中。封面第一次会作为永久素材上传，
之后相同文件会复用 `.cache/cover-media.json` 中的 `media_id`。若后台删除了
该素材，可强制重传：

```powershell
python main.py push --refresh-cover
```

## 3. 定时执行

常驻运行方式：

```powershell
python main.py schedule
```

运行本地测试：

```powershell
python -m unittest discover -s tests -v
```

执行时间由 `.env` 的 `PUSH_CRON` 控制，格式为 `分 时 日 月 周`。例如：

```text
0 9 * * 1      每周一 09:00
30 18 * * 5    每周五 18:30
0 10 1 * *     每月 1 日 10:00
```

服务器或长期运行的电脑上，更推荐使用 Windows 任务计划程序或 Linux cron，
定时执行 `python main.py push`，这样无需让 Python 进程一直驻留。

## HTML 约定

- 标题按 `ARTICLE_TITLE`、`<meta name="wechat:title">`、`<title>`、`<h1>`
  的顺序读取。
- 正文取 `<body>` 内部内容。
- `<img src>` 支持相对路径、绝对路径、HTTP(S) 地址和 base64 data URI。
- 非微信域名图片会先上传到微信，再把 `src` 替换成微信返回的 URL。
- `<script>` 和 `<noscript>` 会被移除。
- CSS 背景图不会自动上传，请改用 `<img>` 或使用已托管在微信的地址。

## 你还需要准备

1. 一个有对应接口权限的微信公众号，及其 `AppID`、`AppSecret`。
2. 在公众号后台把运行程序的服务器公网 IP 加入接口 IP 白名单。
3. 一张符合微信要求的 JPG/PNG 封面图。
4. 最终 HTML 内容，以及文章标题、作者、摘要等信息。
5. 一台到执行时间仍在线、可以访问 `api.weixin.qq.com` 的电脑或服务器。
6. 若账号没有草稿箱或素材接口权限，需要由公众号管理员开通/认证相应能力。

不要提交 `.env`；其中的 `AppSecret` 等同于账号密码，应由管理员妥善保管并
定期轮换。

## 常见问题

- `40164`：当前出口公网 IP 不在公众号白名单。
- `40013` / `40125`：`AppID` 或 `AppSecret` 不正确。
- `48001`：公众号没有该 API 权限。
- `40007`：缓存的封面素材已被删除，使用 `--refresh-cover` 重传。
- 样式与浏览器不同：公众号会过滤部分 HTML/CSS，复杂排版需要在真机预览。
