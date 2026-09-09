# -*- coding: utf-8 -*-
"""全流程编排：模块 1 → 转换 → 模块 2~4 → 图片 → docx + 微信 html。

运行纪律（与 docs/ARCHITECTURE.md 一致）：
- 全部通过子进程调用各模块，模块失败即中断，绝不拿旧文件继续推；
- 每一步产物先写 data/work/{date}/，最终可审核物写 review/{date}/；
- 每次运行写 data/runs/{ts}.json 清单，并更新 data/state.json。
- 所有阶段在终端实时显示进度；长时间无输出的阶段有心跳提示。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from . import convert, docx_builder, html_wechat, images, state as state_mod
from .config import Settings

STAGE_OK = "ok"


class OrchestratorError(RuntimeError):
    pass


def _emit(text: str) -> None:
    print(text, flush=True)


def _create_next_review_dir(review_root: Path, date: str) -> tuple[Path, str]:
    """创建当天的下一个版本；存在任意历史版本时永远接最高 vN 递增。"""
    review_root.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(rf"^{re.escape(date)}-v(\d+)$")
    versions: list[int] = []
    if (review_root / date).exists():
        versions.append(0)
    for path in review_root.iterdir():
        match = pattern.fullmatch(path.name)
        if path.is_dir() and match:
            versions.append(int(match.group(1)))
    version = max(versions, default=-1) + 1
    while True:
        suffix = "" if version == 0 else f"-v{version}"
        candidate = review_root / f"{date}{suffix}"
        try:
            candidate.mkdir(parents=False, exist_ok=False)
            return candidate, suffix
        except FileExistsError:
            version += 1


def _run_live(cmd: list[str], *, prefix: str = "", cwd: Path | None = None,
              env: dict[str, str] | None = None, heartbeat: int = 25,
              on_line=None) -> None:
    """运行子进程并逐行实时转发输出；长时无输出时打印心跳提示。

    heartbeat=0 表示关闭心跳。
    on_line：提供后不再自动打印每行，而是把每行交给该回调（用于进度条等场景）。
    """
    started = time.monotonic()
    proc_env = dict(env) if env is not None else dict(os.environ)
    proc_env.setdefault("PYTHONUNBUFFERED", "1")  # 子进程逐行实时输出，不做块缓冲
    proc = subprocess.Popen(
        cmd, cwd=str(cwd) if cwd else None, env=proc_env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(heartbeat):
            secs = int(time.monotonic() - started)
            _emit(f"[{prefix}⏳] 已进行 {secs} 秒，暂无新输出（长文本生成/网络等待属正常，请耐心）")

    thread = None
    if heartbeat > 0:
        thread = threading.Thread(target=beat, daemon=True)
        thread.start()

    tail: list[str] = []
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        tail.append(line)
        tail = tail[-20:]
        if on_line is not None:
            on_line(line)
        else:
            _emit(f"[{prefix}] {line}")
    rc = proc.wait()
    stop.set()
    if thread is not None:
        thread.join(timeout=1)
    if rc != 0:
        raise OrchestratorError(f"阶段 [{prefix}] 失败（rc={rc}）：\n" + "\n".join(tail[-12:]))


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m} 分 {s} 秒" if m else f"{s} 秒"


def _http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


class Orchestrator:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or Settings()
        self.state = state_mod.StateStore(self.s)

    # ---------- 本地模型服务自动拉起 ----------
    def _local_health_url(self) -> str:
        parsed = urllib.parse.urlsplit(self.s.local_base_url)
        netloc = parsed.netloc or f"127.0.0.1:{parsed.port or 8080}"
        return f"{parsed.scheme or 'http'}://{netloc}/health"

    def _local_llm_ok(self) -> bool:
        return _http_ok(self._local_health_url())

    def ensure_local_llm(self) -> None:
        """provider=local 时确保本地推理服务可用；不可用则自动拉起并等待就绪。"""
        if self.s.effective_provider() != "local":
            return
        if self._local_llm_ok():
            return
        exe = self.s.llm_dir / "engine" / "llama-server.exe"
        model = self.s.llm_dir / "models" / self.s.llm_model_file
        if not exe.exists() or not model.exists():
            raise OrchestratorError(
                "本地模型服务未运行且未找到模型文件：\n"
                f"  引擎: {exe}\n  模型: {model}\n"
                "处理方式（二选一）：\n"
                "  A. 运行 llm\\start-llm.ps1 手动启动本地模型；\n"
                "  B. 在 AI-Daily-Workflow\\.env 填写 DEEPSEEK_API_KEY 改用 DeepSeek。")
        _emit("正在自动启动本地模型服务（首次约 10~30 秒）…")
        self.s.logs_dir.mkdir(parents=True, exist_ok=True)
        log_fh = open(self.s.logs_dir / "local-llm.log", "ab")
        args = ["-m", str(model), "--host", "127.0.0.1", "--port",
                str(urllib.parse.urlsplit(self.s.local_base_url).port or 8080),
                "-ngl", "99", "-c", "16384", "-np", "1", "--alias", "qwen3.5-9b"]
        try:
            subprocess.Popen([str(exe)] + args, stdout=log_fh, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            raise OrchestratorError(f"本地模型启动失败：{exc}") from exc
        t0 = time.monotonic()
        while time.monotonic() - t0 < 180:
            if self._local_llm_ok():
                _emit(f"✓ 本地模型服务就绪（{int(time.monotonic() - t0)} 秒）")
                return
            time.sleep(3)
        raise OrchestratorError("本地模型服务启动超时，请查看 logs\\local-llm.log，或改填 DeepSeek Key")

    # ---------- 单步 ----------
    _SRC_DONE = re.compile(r"^\s*[^:：]{1,60}\s*[：:]\s*(\d+\s*条|失败|错误)")

    def _crawl_source_total(self) -> int:
        """按 sources.json 估算本次要处理的数据源数量（用于进度条分母）。"""
        try:
            cfg = json.loads((self.s.crawler_dir / "sources.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        total = 0
        for key in ("newsnow_sources", "rss_sources"):
            arr = cfg.get(key)
            if isinstance(arr, list):
                total += sum(1 for it in arr if it.get("enabled", True))
        for key in ("hackernews", "arxiv"):
            v = cfg.get(key)
            if isinstance(v, dict) and v.get("enabled", True):
                total += 1
        return total

    def _crawl(self, date: str, use_sample: bool) -> Path:
        if use_sample:
            src = self.s.data_dir / "sample" / "sample_items.json"
            dst = self.s.data_dir / "work" / date / "crawl_items.json"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            _emit("✓ 使用内置样例数据（离线联调模式，不联网爬取）")
            return dst
        out_root = self.s.crawl_output_dir
        cmd = [sys.executable, str(self.s.crawler_dir / "ai_daily.py"), self.s.crawl_edition,
               "--hours", str(self.s.crawl_hours), "--min-score", str(self.s.crawl_min_score),
               "--output-dir", str(out_root)]
        extra = (self.s.crawl_extra_args or "").split()

        # 进度条：按 30 个数据源逐条完成刷新
        total = self._crawl_source_total()
        state: dict = {"n": 0, "last": "", "prev_pct": -1, "prev_n": -1}

        def _draw(note: str = "") -> None:
            n = state["n"]
            if total > 0:
                pct = min(100, int(n * 100 / total))
                if pct != state["prev_pct"]:
                    state["prev_pct"] = pct
                    blocks = pct // 5
                    bar = "█" * blocks + "░" * (20 - blocks)
                    suffix = f" · {note}" if note else ""
                    _emit(f"[爬虫进度 {bar} {pct:3d}%] {n}/{total} 个数据源{suffix}")
                    if pct >= 100:
                        _emit("✓ 爬虫已处理全部数据源，正在汇总去重…")
            else:
                if n != state["prev_n"]:
                    state["prev_n"] = n
                    _emit(f"[爬虫进度] 已处理 {n} 个数据源{(' · ' + note) if note else ''}")

        def on_line(line: str) -> None:
            if self._SRC_DONE.match(line):
                state["n"] += 1
                state["last"] = re.sub(r"\s+", " ", line).strip()[:42]
            _draw(state["last"])

        _run_live(cmd + extra, cwd=self.s.crawler_dir, heartbeat=20, on_line=on_line)
        _emit(f"✓ 爬虫运行结束（完成 {state['n']} 条数据源输出）")
        crawl_json = out_root / date / f"{date}_{self.s.crawl_edition}.json"
        if not crawl_json.exists():
            raise OrchestratorError(f"爬虫结束但未找到输出：{crawl_json}")
        self._enrich_crawl_images(crawl_json)
        return crawl_json

    def _enrich_crawl_images(self, crawl_json: Path) -> None:
        """爬取阶段图片登记：为头部候选条目登记原文页图片 URL（失败不影响流程）。

        登记结果写回 item["images"]，选文后的配图下载直接用登记结果，
        不再依赖"生成那一刻再现场抓页面"。
        """
        try:
            payload = json.loads(crawl_json.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _emit(f"⚠ 图片登记跳过（读取爬取结果失败：{exc}）")
            return
        items = payload.get("items") or []
        if not items:
            return
        t0 = time.monotonic()
        _emit(f"正在登记候选文章配图（前 {min(len(items), self.s.top_candidates)} 条，"
              "失败项自动跳过）…")
        done = images.enrich_items(items, limit=self.s.top_candidates)
        try:
            payload["items"] = items
            crawl_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        except OSError as exc:
            _emit(f"⚠ 图片登记写回失败：{exc}")
            return
        _emit(f"✓ 图片登记完成：{done}/{len(items[:self.s.top_candidates])} 条候选带图"
              f"（耗时 {_fmt_duration(time.monotonic() - t0)}）")

    def _summarize(self, date: str, raw_txt: Path, work_dir: Path,
                   feedback: Path | None) -> tuple[Path, Path]:
        source_html = work_dir / "article_source.html"
        report = work_dir / "scoring_report.json"
        cmd = [sys.executable, str(self.s.summarize_dir / "run.py"),
               "--raw", str(raw_txt),
               "--output", str(source_html),
               "--report", str(report)]
        if feedback and feedback.exists() and feedback.read_text(encoding="utf-8").strip():
            cmd += ["--feedback", str(feedback)]
            _emit("✓ 检测到人工反馈，将按反馈意见筛选/改写")
        env = {**os.environ, **self.s.summarize_env(raw_txt, source_html, report)}
        _run_live(cmd, prefix="成稿", env=env, cwd=self.s.summarize_dir, heartbeat=25)
        if not source_html.exists() or not report.exists():
            raise OrchestratorError("模块 2~4 成功但缺少输出文件")
        return source_html, report

    # ---------- 主流程 ----------
    def run_today(self, date: str | None = None, *, use_sample: bool = False,
                  fetch_images: bool = True, feedback: Path | None = None) -> dict:
        date = date or datetime.now().strftime("%Y-%m-%d")
        # 日期也用于目录名，必须先校验，不能让清理操作越过 review 根目录。
        try:
            if datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d") != date:
                raise ValueError(date)
        except ValueError as exc:
            raise OrchestratorError("日期必须为 YYYY-MM-DD") from exc
        self.state.record_last(date, self.s.crawl_edition, "running", "正在生成")
        try:
            return self._generate_today(date, use_sample=use_sample,
                                        fetch_images=fetch_images, feedback=feedback)
        except (Exception, KeyboardInterrupt) as exc:
            message = "用户取消生成" if isinstance(exc, KeyboardInterrupt) else str(exc)
            self.state.record_last(date, self.s.crawl_edition, "failed", message)
            run_dir = self.s.data_dir / "runs"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")).write_text(
                json.dumps({"date": date, "edition": self.s.crawl_edition,
                            "status": "failed", "error": message,
                            "created_at": datetime.now().isoformat(timespec="seconds")},
                           ensure_ascii=False, indent=2), encoding="utf-8")
            if isinstance(exc, (KeyboardInterrupt, OrchestratorError)):
                raise
            raise OrchestratorError(message) from exc

    def _generate_today(self, date: str, *, use_sample: bool = False,
                        fetch_images: bool = True, feedback: Path | None = None) -> dict:
        total_t0 = time.monotonic()
        date = date or datetime.now().strftime("%Y-%m-%d")
        edition = self.s.crawl_edition
        # 版本化：同一天重复生成不覆盖旧版，依次生成 {date}、{date}-v1、{date}-v2…
        review_dir, suffix = _create_next_review_dir(self.s.review_dir, date)
        work_dir = self.s.data_dir / "work" / f"{date}{suffix}"
        work_dir.mkdir(parents=True, exist_ok=True)
        _emit(f"本版产物目录：{review_dir.name}" if suffix else "")
        # 反馈文件默认约定：data/work/{date}/feedback.txt；显式传入则优先
        if feedback is None:
            auto_fb = self.s.data_dir / "work" / date / "feedback.txt"
            feedback = auto_fb if auto_fb.exists() else None
        attachments = review_dir / "attachments"
        attachments.mkdir(parents=True, exist_ok=True)

        _emit("")
        _emit("=" * 64)
        _emit(f"开始生成 {date} 的每日资讯（模式：{'样例(离线)' if use_sample else '真实爬取'}）")
        _emit("=" * 64)

        # 本地模型引擎：未运行则自动拉起（DeepSeek 模式跳过）
        if self.s.effective_provider() == "local":
            _emit("（检测本地模型引擎…）")
            self.ensure_local_llm()

        # ① 爬取
        _emit("\n① 正在抓取资讯（下方会实时刷新各数据源进度）…")
        crawl_json = self._crawl(date, use_sample)
        # 把本版爬取快照（含已登记图片 URL）留存到版本工作目录，避免被同日再跑覆盖
        staged = work_dir / "crawl_items.json"
        try:
            if staged.resolve() != crawl_json.resolve():
                shutil.copyfile(crawl_json, staged)
            crawl_json = staged
        except OSError as exc:
            raise OrchestratorError(f"爬取结果写入工作目录失败：{exc}") from exc
        item_count = len(convert.load_crawl_items(crawl_json, top=10 ** 9))
        _emit(f"✓ ① 爬取完成：候选资讯 {item_count} 条（耗时 {_fmt_duration(time.monotonic() - total_t0)}）")

        # ② AI 清洗与成稿
        provider = self.s.effective_provider()
        model = self.s.deepseek_model if provider == "deepseek" else self.s.local_model
        _emit(f"\n② AI 清洗与成稿中（引擎：{'DeepSeek' if provider == 'deepseek' else '本地 ' + model}，"
              f"预计 1~5 分钟）…")
        raw_txt = convert.build_raw_txt(crawl_json, work_dir / "raw_news.txt",
                                        top=self.s.top_candidates)
        source_html, report = self._summarize(date, raw_txt, work_dir, feedback)
        _emit(f"✓ ② 成稿完成（耗时 {_fmt_duration(time.monotonic() - total_t0)}）")

        selected = []
        try:
            selected = (json.loads(report.read_text(encoding="utf-8")) or {}).get("selected") or []
        except (ValueError, OSError) as exc:
            raise OrchestratorError(f"读取评分报告失败：{exc}") from exc
        if len(selected) != 5:
            raise OrchestratorError(f"评分报告中有 {len(selected)} 篇入选文章（模块 2~4 必须选满 5 篇）")
        for i, c in enumerate(selected, 1):
            _emit(f"   入选 {i}：{c.get('title', '')[:50]}（{float(c.get('total_score') or 0):.1f} 分）")

        # ③ 配图（用爬取阶段登记的图片 URL；选文后直接下载，与 LLM 无关）
        images_map: dict[int, list[Path]] = {}
        if fetch_images and self.s.fetch_images.lower() in ("1", "true", "yes", "on"):
            _emit(f"\n③ 正在为入选文章下载配图（每篇最多 {self.s.images_per_news} 张，"
                  "实在无图时自动补默认题图）…")
            crawl_items = []
            try:
                crawl_items = convert.load_crawl_items(crawl_json, top=10 ** 9)
            except (OSError, ValueError):
                crawl_items = []
            fallback_img = self.s.root / "app" / "assets" / "default-news.jpg"
            images.ensure_default_banner(fallback_img)
            fallback = fallback_img if fallback_img.exists() else None
            images_map = images.fetch_selected(selected, attachments,
                                               per_news=self.s.images_per_news,
                                               crawl_items=crawl_items,
                                               fallback_image=fallback)
            for idx in sorted(images_map):
                files = images_map[idx]
                if files:
                    _emit(f"   ✓ 第 {idx} 篇配图 {len(files)} 张 → {files[0].parent.name}")
                else:
                    _emit(f"   - 第 {idx} 篇未抓到可用图片（原网页无图/反爬，不影响成稿）")
        else:
            _emit("\n③ 已跳过配图抓取（--no-images 或 FETCH_IMAGES=false）")

        # ④ 封面 + 排版
        first_image = next((v[0] for k in sorted(images_map) for v in [images_map[k]] if v), None)
        if first_image:
            cover = review_dir / "cover.jpg"
            shutil.copyfile(first_image, cover)
        else:
            fallback = self.s.wechat_dir / "content" / "test.png"
            cover = review_dir / "cover.png"
            if fallback.exists():
                shutil.copyfile(fallback, cover)
            else:
                cover = Path("")  # 无封面时模块 6 会报错，让用户知晓

        _emit("\n④ 生成公众号 HTML / Word 新闻稿…")
        final_html = html_wechat.build_wechat_html(source_html, review_dir / "article.html",
                                                   images_map)
        docx_path = docx_builder.build_docx(final_html, review_dir / f"新闻稿_{date}.docx")

        manifest = {
            "date": date, "edition": edition, "status": STAGE_OK, "created_at": datetime.now().isoformat(timespec="seconds"),
            "crawl_json": str(crawl_json), "raw_txt": str(raw_txt),
            "source_html": str(source_html), "scoring_report": str(report),
            "article_html": str(final_html), "docx": str(docx_path),
            "cover": str(cover) if cover != Path("") else "",
            "review_dir": str(review_dir),
            "attachments": str(attachments),
            "news_count": len(selected), "image_groups": {str(k): [str(p) for p in v] for k, v in images_map.items()},
        }
        run_dir = self.s.data_dir / "runs"
        run_dir.mkdir(parents=True, exist_ok=True)
        run_file = run_dir / (datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
        run_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self.state.record_last(date, edition, "ok", f"已生成 {len(selected)} 篇成稿", str(review_dir))

        _emit(f"\n全部完成！总耗时 {_fmt_duration(time.monotonic() - total_t0)}")
        _emit("=" * 64)
        return manifest

    # ---------- 审核通过 → 推送 ----------
    def _latest_review_dir(self, date: str) -> Path:
        """某日期的最高版本审核目录：{date}、{date}-v1、{date}-v2…取最新存在者。"""
        base = self.s.review_dir / date
        if not base.exists():
            version = 1
            while True:
                cand = self.s.review_dir / f"{date}-v{version}"
                if not cand.exists():
                    break
                base = cand
                version += 1
        return base

    def push_reviewed(self, date: str | None = None, *, article_path: Path | None = None) -> dict:
        last = self.state.read().last_run
        date = date or (last.date or datetime.now().strftime("%Y-%m-%d"))
        article = (article_path if article_path is not None else self.s.review_dir / date / "article.html").resolve()
        if not article.is_relative_to(self.s.review_dir.resolve()) or article.suffix.lower() not in (".html", ".htm"):
            raise OrchestratorError("请选择 review 目录内的 HTML 稿件")
        review_dir = article.parent
        date = review_dir.name
        if last.date == date and last.status != STAGE_OK:
            raise OrchestratorError(f"{date} 最近一次生成未成功（{last.status}），请重新生成并审核后推送")
        if not article.is_file():
            raise OrchestratorError(f"未找到待审核文件：{article}（请先运行 today 生成）")
        cover = (review_dir / "cover.jpg") if (review_dir / "cover.jpg").exists() else review_dir / "cover.png"
        if not cover.exists():
            raise OrchestratorError(f"缺少封面文件：{cover}")
        errors = self.s.validate_wechat()
        if errors:
            raise OrchestratorError("微信配置不完整：" + "；".join(errors))
        _emit(f"上传文件：{article}")
        _emit(f"封面文件：{cover}")
        _emit(f"正在上传到公众号草稿箱（标题：{self.s.article_title or f'AI 每日资讯 {date}'}）…")
        # 公众号草稿标题有长度限制：未配置 ARTICLE_TITLE 时用简短默认标题（老大事后可在草稿箱改）
        env = {**os.environ, **self.s.wechat_env(article, cover, default_title=f"AI 每日资讯 {date}")}
        _run_live([sys.executable, str(self.s.wechat_dir / "main.py"), "push"],
                  prefix="微信", cwd=self.s.wechat_dir, env=env, heartbeat=30)
        _emit("✓ 已推送：公众号后台 → 草稿箱可预览（编辑/发布）")
        return {"date": date, "pushed": True}
