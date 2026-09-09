# -*- coding: utf-8 -*-
"""图片采集与标准化（与语言模型完全无关，纯爬取/HTTP 环节）。

两段式设计：
1) 爬取阶段 enrich_items()：为候选条目登记原文页的图片 URL（写入 item["images"]）；
2) 成稿阶段 fetch_selected()：对入选的每篇新闻，从登记 URL 下载图片并统一转
   JPEG 存到 review/{date}/attachments/{NN}-{slug}/（未登记到再现场回源页面）。
全部失败不报错，只影响配图数量。
"""
from __future__ import annotations

import re
import shutil
import time
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from PIL import Image, UnidentifiedImageError

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
IMAGE_CT_RE = re.compile(r"^image/")
MAX_IMAGE_BYTES = 8 * 1024 * 1024
_SESSION = None

# 常见反爬/登录墙域名：登记时直接跳过，不浪费时间
SKIP_HOSTS = {"x.com", "twitter.com", "weibo.com", "m.weibo.cn", "facebook.com"}


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update(UA)
        s.mount("https://", requests.adapters.HTTPAdapter(max_retries=1))
        s.mount("http://", requests.adapters.HTTPAdapter(max_retries=1))
        _SESSION = s
    return _SESSION


def slugify(title: str, max_len: int = 24) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title).strip("-").lower()
    return (text or "item")[:max_len]


def discover_images(page_url: str, timeout: float = 6.0, limit: int = 4) -> list[str]:
    """返回页面中值得下载的图片 URL（og:image 优先，其次前几个 <img>）。"""
    try:
        if urlsplit(page_url).hostname in SKIP_HOSTS:
            return []
        resp = _session().get(page_url, timeout=timeout)
        if resp.status_code != 200 or not resp.headers.get("Content-Type", "").startswith("text/html"):
            return []
        html = resp.text
    except requests.RequestException:
        return []
    found: list[str] = []
    for prop in ("og:image", "og:image:secure_url", "og:image:url",
                 "twitter:image", "twitter:image:src"):
        m = re.search(rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)', html, re.I)
        if not m:
            m = re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']', html, re.I)
        if m:
            found.append(m.group(1).strip())
            break
    m = re.search(r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)', html, re.I)
    if not m:
        m = re.search(r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']image_src["\']', html, re.I)
    if m:
        found.append(m.group(1).strip())
    for src in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I)[:20]:
        u = src.strip()
        if u.startswith("data:") or u.startswith("//"):
            if u.startswith("//"):
                u = "https:" + u
            else:
                continue
        if u.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")) or "image" in u.lower():
            found.append(u)
    # 只取前 limit 个、去重、过滤明显小图标域名
    seen: set[str] = set()
    out: list[str] = []
    for u in found:
        if u in seen or not u.lower().startswith(("http://", "https://")):
            continue
        if any(k in u.lower() for k in ("logo", "avatar", "icon", "sprite", "favicon", "pixel", "track")):
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= limit:
            break
    return out


def normalize_url(url: str) -> str:
    """URL 规整：去掉跟踪参数与尾斜杠，用于条目与选文的匹配。"""
    try:
        parts = urlsplit(url.strip())
        query = [kv for kv in parse_qsl(parts.query, keep_blank_values=True)
                 if not kv[0].lower().startswith("utm_")]
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path,
                           urlencode(query), ""))
    except ValueError:
        return url.strip()


def enrich_items(items: list[dict], limit: int = 60, workers: int = 6,
                 timeout: float = 5.0) -> int:
    """爬取阶段：为候选条目登记原文页图片 URL（写入 item["images"]，失败置空）。

    只处理前 limit 条（已是按分数排序的头部候选）；并发受限、单条超时短，
    失败不影响爬取结果。返回成功登记到图片的条数。
    """
    jobs = []
    for item in items[:limit]:
        url = (item.get("url") or "").strip()
        if not url.lower().startswith("http"):
            item["images"] = []
            continue
        jobs.append(item)
    if not jobs:
        return 0

    def _probe(item: dict) -> None:
        try:
            item["images"] = discover_images(item["url"], timeout=timeout, limit=4)
        except Exception:  # noqa: BLE001
            item["images"] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_probe, item) for item in jobs]
        for _ in as_completed(futures):
            pass
    return sum(1 for item in jobs if item.get("images"))


def download_image(url: str, timeout: float = 8.0) -> bytes | None:
    try:
        resp = _session().get(url, timeout=timeout, stream=True)
        if resp.status_code != 200:
            return None
        ctype = resp.headers.get("Content-Type", "")
        if ctype and not IMAGE_CT_RE.match(ctype):
            return None
        data = resp.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
        return data if len(data) <= MAX_IMAGE_BYTES else None
    except requests.RequestException:
        return None


def normalize_jpeg(data: bytes, dest: Path, max_side: int = 1400, quality: int = 82) -> bool:
    """转 JPEG（微信/公众号最兼容），超宽图缩小；返回是否成功。"""
    try:
        img = Image.open(__import__("io").BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError):
        return False
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="JPEG", quality=quality, optimize=True)
    return True


def _dhash_image(image: Image.Image, size: int = 16) -> int:
    """对重新压缩、缩放和轻微裁切较稳定的差值哈希。"""
    gray = image.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    pixels = gray.load()
    value = 0
    for y in range(size):
        for x in range(size):
            if pixels[x, y] > pixels[x + 1, y]:
                value |= 1 << (y * size + x)
    return value


def _dhash_bytes(data: bytes) -> int | None:
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            return _dhash_image(image)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _dhash_path(path: Path) -> int | None:
    try:
        with Image.open(path) as image:
            image.load()
            return _dhash_image(image)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _save_from_urls(urls: list[str], dest_dir: Path, per_news: int, timeout: float,
                    existing: list[Path] | None = None) -> list[Path]:
    """下载并转 JPEG；URL 不同但视觉近似的重复图也会跳过。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    existing = list(existing or [])
    fingerprints = [value for path in existing if (value := _dhash_path(path)) is not None]
    seen: set[str] = set()
    for url in urls:
        if len(saved) >= per_news:
            break
        u = url.strip()
        if not u.lower().startswith(("http://", "https://")) or u in seen:
            continue
        seen.add(u)
        data = download_image(u, timeout=timeout)
        if not data:
            continue
        fingerprint = _dhash_bytes(data)
        if fingerprint is not None and any((fingerprint ^ old).bit_count() <= 10
                                           for old in fingerprints):
            continue
        out = dest_dir / f"{len(existing) + len(saved) + 1:02d}.jpg"
        if normalize_jpeg(data, out):
            saved.append(out)
            if fingerprint is not None:
                fingerprints.append(fingerprint)
        time.sleep(0.2)
    return saved


def fetch_for_item(page_url: str, title: str, dest_dir: Path,
                   per_news: int = 3, timeout: float = 6.0,
                   known_urls: list[str] | None = None) -> list[Path]:
    """抓取一条新闻的配图（优先用 known_urls 已登记图片，否则现场回源页面）。"""
    urls = list(known_urls or [])
    if not urls:
        urls = discover_images(page_url, timeout=timeout, limit=per_news * 2)
    return _save_from_urls(urls, dest_dir, per_news, timeout)


def _index_crawl_items(crawl_items: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for item in crawl_items:
        for key in ("url", "canonical_url"):
            if item.get(key):
                index.setdefault(normalize_url(str(item[key])), item)
    return index


def _alt_source_urls(item: dict | None, main_url: str, limit: int = 2) -> list[str]:
    """同一新闻的其他来源链接（去重、去跟踪参数、排除与主链接相同者）。"""
    out: list[str] = []
    if not item:
        return out
    main_norm = normalize_url(main_url)
    for source in item.get("sources") or []:
        u = (source.get("url") or "").strip()
        if u.lower().startswith(("http://", "https://")) and normalize_url(u) != main_norm:
            if u not in out:
                out.append(u)
        if len(out) >= limit:
            break
    return out


def ensure_default_banner(path: Path, size: tuple[int, int] = (1200, 630)) -> None:
    """生成一张中性默认题图（渐变底 + 几何图案，无文字，避免缺字体问题）。

    某条新闻确实找不到任何图时作为兜底，保证"每条新闻都有图"。
    """
    if path.exists() and path.stat().st_size > 5000:
        return
    try:
        from PIL import Image, ImageDraw
        width, height = size
        img = Image.new("RGB", (width, height))
        px = img.load()
        top = (37, 99, 235)
        bottom = (17, 24, 60)
        for y in range(height):
            t = y / max(height - 1, 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            for x in range(width):
                px[x, y] = (r, g, b)
        draw = ImageDraw.Draw(img)
        for cx, cy, rad in ((int(width * 0.8), int(height * 0.2), 190),
                            (int(width * 0.15), int(height * 0.85), 240),
                            (int(width * 0.6), int(height * 0.9), 120)):
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(255, 255, 255), width=3)
            draw.ellipse([cx - rad // 2, cy - rad // 2, cx + rad // 2, cy + rad // 2],
                         outline=(255, 255, 255), width=2)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(path), format="JPEG", quality=85)
    except Exception:  # noqa: BLE001
        pass


def fetch_selected(selected: list[dict], attachments_root: Path,
                   per_news: int = 3, timeout: float = 6.0,
                   crawl_items: list[dict] | None = None,
                   fallback_image: Path | None = None) -> dict[int, list[Path]]:
    """为 selected[]（来自 scoring_report.json）逐条抓图，尽量保证每条至少有图。

    取图顺序：爬取阶段登记 URL → 原文页现场发现 → 同新闻其他来源链接 →
    全部失败时复制默认题图兜底。返回 {序号(1 起): [jpg...]}。
    """
    index = _index_crawl_items(crawl_items or [])
    result: dict[int, list[Path]] = {}
    for idx, cand in enumerate(selected, 1):
        url = (cand.get("source_url") or "").strip()
        title = (cand.get("title") or f"news-{idx}").strip()
        folder = attachments_root / f"{idx:02d}-{slugify(title)}"
        if not url:
            result[idx] = []
            continue
        item = index.get(normalize_url(url))
        known: list[str] = list(item.get("images") or []) if item else []
        alts = _alt_source_urls(item, url)
        saved: list[Path] = []

        # 1) 登记图
        if known:
            saved = _save_from_urls(known, folder, per_news, timeout)
        # 2) 原文页现场发现（登记为空时）
        if len(saved) < per_news:
            discovered = [] if known else discover_images(url, timeout=timeout, limit=per_news * 3)
            saved += _save_from_urls([u for u in discovered], folder,
                                     per_news - len(saved), timeout, existing=saved)
        # 3) 同新闻的其他来源链接
        for alt in alts:
            if len(saved) >= per_news:
                break
            alt_found = discover_images(alt, timeout=timeout, limit=per_news * 3)
            saved += _save_from_urls(alt_found, folder, per_news - len(saved), timeout,
                                     existing=saved)
        # 4) 默认题图兜底：保证每条新闻都有图
        if not saved and fallback_image and fallback_image.exists():
            dest = folder / "01.jpg"
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fallback_image, dest)
            saved = [dest]
        result[idx] = saved
    return result
