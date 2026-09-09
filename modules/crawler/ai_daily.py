#!/usr/bin/env python3
"""AI Daily module 1: multi-source AI industry news collection."""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    requests = None


SCHEMA_VERSION = "2.0"
SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_FILE = SKILL_DIR / "sources.json"
DEFAULT_OUTPUT_BASE = SKILL_DIR / "output" / "crawl"
CHINA_TIMEZONE = timezone(timedelta(hours=8))
TRACKING_QUERY_KEYS = {
    "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "source",
    "spm", "from", "share_source", "utm_campaign", "utm_content",
    "utm_medium", "utm_source", "utm_term",
}


def _literal_pattern(*terms):
    parts = []
    for term in terms:
        escaped = re.escape(term)
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .+/_-]*", term):
            escaped = rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
        parts.append(escaped)
    return re.compile("|".join(parts), re.IGNORECASE)


def _rules(groups):
    return [(label, _literal_pattern(*terms)) for label, terms in groups]


CORE_AI_RULES = _rules([
    ("AI", ["AI", "人工智能", "生成式AI", "生成式人工智能"]),
    ("机器学习", ["机器学习", "深度学习", "强化学习"]),
    ("大模型", ["大模型", "基础模型", "LLM", "多模态", "推理模型"]),
    ("模型工程", ["模型训练", "模型推理", "模型部署", "模型蒸馏", "预训练", "后训练", "微调"]),
    ("智能体", ["智能体", "Agent", "AI Agent", "RAG"]),
    ("生成模型", ["AIGC", "Diffusion", "Stable Diffusion", "文生图", "文生视频"]),
    ("OpenAI", ["OpenAI", "ChatGPT", "GPT"]),
    ("Anthropic", ["Anthropic", "Claude"]),
    ("Google AI", ["Gemini", "DeepMind"]),
    ("DeepSeek", ["DeepSeek"]),
    ("国内模型", ["文心一言", "通义千问", "豆包", "Kimi", "智谱", "百川智能", "月之暗面", "混元", "盘古大模型", "讯飞星火", "MiniMax", "阶跃星辰", "零一万物"]),
    ("生成产品", ["Midjourney", "Sora", "可灵", "即梦"]),
    ("模型生态", ["参数量", "上下文窗口", "模型开源", "开源模型", "闭源模型", "端侧模型", "端侧AI", "提示词", "prompt"]),
    ("AI治理", ["AI安全", "模型安全", "AI监管", "AI治理", "训练数据", "合成数据", "数据标注"]),
])

INFRA_RULES = _rules([
    ("英伟达", ["英伟达", "NVIDIA", "黄仁勋"]),
    ("AMD", ["AMD", "苏姿丰"]),
    ("国产AI芯片", ["昇腾", "Ascend", "海光", "海光信息", "Hygon", "寒武纪", "Cambricon", "壁仞", "燧原", "沐曦", "摩尔线程", "天数智芯", "瀚博半导体", "澜起科技", "芯原股份", "景嘉微", "平头哥", "地平线机器人", "黑芝麻智能"]),
    ("存储", ["海力士", "SK海力士", "SK hynix", "三星电子", "Samsung", "美光", "Micron", "铠侠", "Kioxia", "西部数据", "Western Digital", "HBM", "HBM2", "HBM2E", "HBM3", "HBM3E", "HBM4", "DRAM", "NAND", "DDR5", "GDDR7", "存储芯片"]),
    ("晶圆代工", ["台积电", "TSMC", "中芯国际", "SMIC", "联电", "UMC", "GlobalFoundries", "三星晶圆"]),
    ("半导体设备", ["ASML", "阿斯麦", "应用材料", "Applied Materials", "泛林", "Lam Research", "东京电子", "Tokyo Electron", "科磊", "KLA", "北方华创", "中微公司", "光刻机", "EDA"]),
    ("芯片设计", ["博通", "Broadcom", "Marvell", "高通", "Qualcomm", "Arm", "联发科", "MediaTek", "Cerebras", "Groq", "Tenstorrent", "Graphcore", "SambaNova"]),
    ("AI处理器", ["GPU", "GPGPU", "AI芯片", "AI加速器", "AI accelerator", "推理芯片", "训练芯片", "NPU", "TPU", "DPU", "ASIC"]),
    ("半导体制造", ["半导体", "晶圆", "先进制程", "先进封装", "CoWoS", "Chiplet", "日月光", "ASE", "Amkor", "长电科技", "通富微电", "华天科技", "长江存储", "YMTC", "长鑫存储", "CXMT"]),
    ("高速互连", ["光模块", "硅光", "CPO", "InfiniBand", "NVLink", "高速互连", "AI交换机", "以太网交换机"]),
    ("算力", ["算力", "智算", "智算中心", "超算", "AI服务器", "推理服务器", "训练服务器", "液冷", "数据中心", "IDC", "Supermicro", "超微电脑"]),
    ("云平台", ["云计算", "Azure", "Google Cloud", "谷歌云", "AWS", "阿里云", "腾讯云", "华为云", "火山引擎"]),
])

APP_RULES = _rules([
    ("自动驾驶", ["自动驾驶", "无人驾驶", "智驾", "智能驾驶", "辅助驾驶", "端到端驾驶", "Robotaxi", "智能座舱"]),
    ("机器人", ["机器人", "具身智能", "人形机器人", "机器狗", "具身"]),
    ("AI终端", ["AI手机", "AI PC", "AI眼镜", "AI搜索", "AI助手"]),
    ("AI软件", ["AI编程", "代码助手", "AI办公", "AI视频", "AI音乐", "AI绘画", "数字人"]),
    ("行业AI", ["AI教育", "AI医疗", "AI制药", "AI营销", "AI客服", "工业智能", "智能制造"]),
    ("智能设备", ["脑机接口", "自动化仓储", "无人配送", "无人机", "飞行汽车"]),
])

AI_NATIVE_COMPANY_RULES = _rules([
    ("AI原生公司", ["OpenAI", "Anthropic", "xAI", "Mistral", "Perplexity", "Cohere", "Runway", "Scale AI", "Hugging Face", "Stability AI", "Character.AI", "Anysphere", "Cursor", "Glean", "ElevenLabs", "Synthesia", "Suno", "Pika"]),
    ("国内AI公司", ["商汤", "旷视", "云从", "科大讯飞", "MiniMax", "阶跃星辰", "零一万物", "月之暗面", "智谱", "百川智能"]),
    ("机器人公司", ["宇树", "Unitree", "智元", "银河通用", "傅利叶", "优必选"]),
])

GENERAL_TECH_COMPANY_RULES = _rules([
    ("科技巨头", ["Google", "谷歌", "Alphabet", "Microsoft", "微软", "Meta", "Apple", "苹果", "Amazon", "亚马逊", "华为", "字节跳动", "ByteDance", "腾讯", "阿里巴巴", "百度"]),
    ("汽车科技", ["Tesla", "特斯拉", "大疆", "DJI"]),
])

BUSINESS_RULES = _rules([
    ("资本", ["融资", "投资", "并购", "IPO", "上市", "独角兽", "估值", "funding", "investment", "acquisition", "valuation"]),
    ("经营", ["财报", "营收", "利润", "裁员", "招聘", "订单", "供应链", "产能", "涨价", "降价", "earnings", "revenue", "profit", "layoff", "hiring", "order", "orders", "capacity", "supply chain"]),
    ("市场", ["市值", "股价", "涨停", "跌停", "港股", "美股", "A股"]),
    ("交易合作", ["合作", "签约", "收购", "拆分", "重组", "补贴", "招标", "采购"]),
    ("政策法律", ["监管", "政策", "制裁", "出口管制", "禁令", "许可", "反垄断", "版权", "诉讼", "regulation", "sanction", "export control", "antitrust", "copyright", "lawsuit"]),
])

NOISE_RULES = _rules([
    ("标题党", ["震惊", "不转不是中国人"]),
    ("博彩", ["开奖", "彩票", "博彩", "赌球", "中奖"]),
    ("娱乐八卦", ["八卦", "绯闻", "恋情", "离婚", "演唱会", "综艺"]),
    ("生活方式", ["减肥", "养生", "食谱", "穿搭", "星座"]),
])


def default_config():
    return {
        "newsnow_base_url": "https://newsnow.busiyi.world/api/s",
        "newsnow_force_latest": False,
        "min_relevance_score": 35,
        "request_timeout_seconds": 20,
        "request_retries": 3,
        "request_interval_seconds": 1.2,
        "lookback_hours": 12,
        "rss_default_max_items": 100,
        "newsnow_sources": [
            {"id": "zhihu", "name": "知乎"}, {"id": "toutiao", "name": "今日头条"},
            {"id": "baidu", "name": "百度热搜"}, {"id": "weibo", "name": "微博"},
            {"id": "bilibili-hot-search", "name": "bilibili热搜"}, {"id": "douyin", "name": "抖音"},
            {"id": "36kr", "name": "36氪", "enabled": False}, {"id": "ithome", "name": "IT之家"},
            {"id": "wallstreetcn-hot", "name": "华尔街见闻"}, {"id": "cls-hot", "name": "财联社热门"},
            {"id": "thepaper", "name": "澎湃新闻"}, {"id": "producthunt", "name": "Product Hunt"},
            {"id": "aihot", "name": "AIHOT"}, {"id": "sspai", "name": "少数派"},
            {"id": "juejin", "name": "稀土掘金"}, {"id": "solidot", "name": "Solidot"},
            {"id": "github-trending-today", "name": "GitHub Trending"},
        ],
        "rss_sources": [
            {"id": "techcrunch-ai", "name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "trusted_ai": True},
            {"id": "openai-news", "name": "OpenAI News", "url": "https://openai.com/news/rss.xml", "trusted_ai": True},
            {"id": "deepmind-blog", "name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml", "trusted_ai": True},
            {"id": "huggingface-blog", "name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml", "trusted_ai": True},
            {"id": "nvidia-blog", "name": "NVIDIA Blog", "url": "https://blogs.nvidia.com/feed/", "trusted_ai": False},
            {"id": "aws-ml-blog", "name": "AWS Machine Learning Blog", "url": "https://aws.amazon.com/blogs/machine-learning/feed/", "trusted_ai": True},
            {"id": "microsoft-blog", "name": "Microsoft Blog", "url": "https://blogs.microsoft.com/feed/", "trusted_ai": False},
            {"id": "mit-ai-news", "name": "MIT AI News", "url": "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml", "trusted_ai": True},
            {"id": "google-ai-blog", "name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/", "trusted_ai": True},
            {"id": "venturebeat-ai", "name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "trusted_ai": True},
            {"id": "google-news-ai-cn", "name": "Google News AI 中文", "url": "https://news.google.com/rss/search?q=%28AI%20OR%20%22%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD%22%20OR%20%22%E5%A4%A7%E6%A8%A1%E5%9E%8B%22%29%20when%3A2d&hl=zh-CN&gl=CN&ceid=CN%3Azh-Hans", "trusted_ai": True, "max_items": 60},
            {"id": "google-news-ai-chip", "name": "Google News AI 芯片", "url": "https://news.google.com/rss/search?q=%28%22AI%E8%8A%AF%E7%89%87%22%20OR%20HBM%20OR%20GPU%20OR%20%22%E6%B5%B7%E5%85%89%22%20OR%20%22%E6%B5%B7%E5%8A%9B%E5%A3%AB%22%29%20when%3A3d&hl=zh-CN&gl=CN&ceid=CN%3Azh-Hans", "trusted_ai": True, "max_items": 60},
        ],
        "hackernews": {"enabled": True, "max_items": 80},
        "arxiv": {"enabled": True, "max_items": 30},
    }


def load_config(path):
    config = default_config()
    config_path = Path(path) if path else DEFAULT_CONFIG_FILE
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            config.update(json.load(f))
    if os.environ.get("AI_DAILY_NEWSNOW_URL"):
        config["newsnow_base_url"] = os.environ["AI_DAILY_NEWSNOW_URL"]
    return config


class HttpClient:
    def __init__(self, timeout=20, retries=3):
        if requests is None:
            raise RuntimeError("缺少 requests，请先运行 bash auto_init.sh")
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(total=retries, connect=retries, read=retries, status=retries, backoff_factor=0.8,
                      status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(["GET"]),
                      respect_retry_after_header=True, raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "application/json, application/rss+xml, application/atom+xml, text/xml, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "X-AI-Daily-Client": "2.0",
        })

    def get(self, url, **kwargs):
        response = self.session.get(url, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response

    def get_json(self, url, **kwargs):
        return self.get(url, **kwargs).json()


def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat(timespec="seconds")


def parse_datetime(value, default_tz=timezone.utc):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(timespec="seconds")
        text = str(value).strip()
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=default_tz)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return None


def within_lookback(published_at, hours):
    if not hours or not published_at:
        return True
    try:
        return datetime.fromisoformat(published_at) >= utc_now() - timedelta(hours=hours)
    except ValueError:
        return True


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(str(value)))).strip()


def _matches(rules, text):
    return [label for label, pattern in rules if pattern.search(text)]


def evaluate_relevance(text, source_floor=0):
    text = clean_text(text)
    noise = _matches(NOISE_RULES, text)
    if noise:
        return {"score": 0, "reason": "低质量/无关内容", "matched_keywords": noise, "confidence": "rejected"}
    core = _matches(CORE_AI_RULES, text)
    infra = _matches(INFRA_RULES, text)
    apps = _matches(APP_RULES, text)
    native = _matches(AI_NATIVE_COMPANY_RULES, text)
    general = _matches(GENERAL_TECH_COMPANY_RULES, text)
    business = _matches(BUSINESS_RULES, text)
    matched = list(dict.fromkeys(core + infra + apps + native + general + business))
    score, reason = 0, ""
    if core:
        score = 70 + min(12, len(infra) * 6) + min(8, len(apps) * 4) + min(5, len(native + general) * 3) + min(5, len(business) * 2)
        reason = "明确 AI 技术/产品"
    elif apps:
        score = 42 + min(8, len(native + general) * 4) + min(5, len(business) * 3) + min(5, len(infra) * 3)
        reason = "AI 应用/智能化场景"
    elif len(infra) >= 2:
        score, reason = 58 + min(7, len(business) * 3), "AI 基础设施/半导体产业链"
    elif infra and (business or native):
        score, reason = 49 + min(8, len(business) * 3), "AI 产业链商业动态"
    elif infra:
        score, reason = 36, "AI 基础设施/半导体候选"
    elif native and business:
        score, reason = 40 + min(8, len(business) * 3), "AI 原生公司动态"
    elif source_floor:
        score, reason = source_floor, "AI 垂直来源"
    score = min(100, score)
    confidence = "high" if score >= 70 else "medium" if score >= 50 else "low" if score else "rejected"
    return {"score": score, "reason": reason, "matched_keywords": matched, "confidence": confidence}


def score_relevance(text):
    result = evaluate_relevance(text)
    return result["score"], result["reason"]


def canonicalize_url(url):
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower() or "https"
        host = parts.netloc.lower().removeprefix("www.") if hasattr(str, "removeprefix") else parts.netloc.lower().lstrip("www.")
        path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if k.lower() not in TRACKING_QUERY_KEYS and not k.lower().startswith("utm_")]
        return urlunsplit((scheme, host, path, urlencode(sorted(query)), ""))
    except ValueError:
        return url.strip()


def normalize_title(title):
    title = clean_text(title).lower()
    title = re.sub(r"^(快讯|突发|独家|重磅|最新)[：:\s-]+", "", title)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title)


def titles_similar(left, right):
    if left == right:
        return True
    if min(len(left), len(right)) < 12:
        return False
    left_numbers = set(re.findall(r"\d+(?:\.\d+)*", left))
    right_numbers = set(re.findall(r"\d+(?:\.\d+)*", right))
    if left_numbers and right_numbers and left_numbers != right_numbers:
        return False
    return SequenceMatcher(None, left, right).ratio() >= 0.9


def build_item(source, rank, title, url="", published_at=None, source_updated_at=None,
               snippet="", external_id="", source_floor=0, extra=None, duplicate_title=None):
    title, snippet = clean_text(title), clean_text(snippet)
    evaluation = evaluate_relevance(f"{title} {snippet}", source_floor=source_floor)
    return {
        "title": title, "url": url or "", "canonical_url": canonicalize_url(url),
        "published_at": published_at, "source_updated_at": source_updated_at, "fetched_at": iso_now(),
        "rank": rank, "source_id": source["id"], "source_name": source["name"], "provider": source["provider"],
        "external_id": str(external_id or ""), "relevance_score": evaluation["score"],
        "confidence": evaluation["confidence"], "match_reason": evaluation["reason"],
        "matched_keywords": evaluation["matched_keywords"], "duplicate_key": normalize_title(duplicate_title or title),
        "snippet": snippet[:500], "extra": extra or {},
    }


def source_status(source, status, started, total=0, matched=0, error="", source_updated_at=None):
    return {
        "source_id": source["id"], "source_name": source["name"], "provider": source["provider"],
        "status": status, "total_items": total, "matched_items": matched,
        "source_updated_at": source_updated_at, "duration_ms": int((time.monotonic() - started) * 1000),
        "error": clean_text(error)[:500],
    }


def collect_newsnow(client, config, min_score, lookback_hours):
    collected, statuses = {}, []
    entries = config.get("newsnow_sources", [])
    entries = [entry for entry in entries if entry.get("enabled", True)]
    for index, entry in enumerate(entries):
        source = {"id": entry["id"], "name": entry["name"], "provider": "newsnow"}
        started = time.monotonic()
        try:
            params = {"id": source["id"]}
            if config.get("newsnow_force_latest"):
                params["latest"] = "1"
            data = client.get_json(config["newsnow_base_url"], params=params)
            api_status = data.get("status")
            if api_status not in ("success", "cache"):
                raise ValueError(f"NewsNow status={api_status}")
            source_updated_at = parse_datetime(data.get("updatedTime"))
            raw_items, items = data.get("items") or [], []
            for rank, raw in enumerate(raw_items, 1):
                if not raw.get("title"):
                    continue
                extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
                published_at = parse_datetime(raw.get("pubDate") or extra.get("date"), default_tz=CHINA_TIMEZONE)
                snippet = " ".join(str(v) for v in [extra.get("hover"), extra.get("info")] if v)
                item = build_item(source, rank, raw["title"], raw.get("url") or raw.get("mobileUrl") or "",
                                  published_at, source_updated_at, snippet, raw.get("id"), extra=extra)
                if item["relevance_score"] >= min_score and within_lookback(item["published_at"], lookback_hours):
                    items.append(item)
            collected[source["id"]] = items
            status_name = "cache" if api_status == "cache" else "success"
            statuses.append(source_status(source, status_name, started, len(raw_items), len(items), source_updated_at=source_updated_at))
            print(f"  {source['name']}: {len(raw_items)} 条，命中 {len(items)} 条 ({status_name})")
        except Exception as exc:
            statuses.append(source_status(source, "failed", started, error=f"{type(exc).__name__}: {exc}"))
            print(f"  {source['name']}: 失败 - {type(exc).__name__}: {exc}")
        if index < len(entries) - 1:
            time.sleep(max(0, float(config.get("request_interval_seconds", 1.2))))
    return collected, statuses


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _first_text(node, names):
    names = set(names)
    for child in node.iter():
        if _local_name(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def _entry_link(node):
    for child in node.iter():
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href and child.attrib.get("rel", "alternate") in ("alternate", ""):
            return href
        if child.text and child.text.strip():
            return child.text.strip()
    return ""


def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    entries = [node for node in root.iter() if _local_name(node.tag) in ("item", "entry")]
    return [{
        "title": _first_text(entry, ["title"]), "url": _entry_link(entry),
        "published_at": parse_datetime(_first_text(entry, ["pubdate", "published", "updated", "date"])),
        "snippet": _first_text(entry, ["description", "summary", "content"]),
        "external_id": _first_text(entry, ["guid", "id"]),
        "publisher": _first_text(entry, ["source"]),
    } for entry in entries]


def remove_publisher_suffix(title, publisher):
    if not publisher:
        return title
    pattern = rf"\s+(?:-|–|—)\s+{re.escape(publisher.strip())}\s*$"
    return re.sub(pattern, "", title, flags=re.IGNORECASE).strip()


def collect_rss(client, config, min_score, lookback_hours):
    collected, statuses = {}, []
    for entry in config.get("rss_sources", []):
        if not entry.get("enabled", True):
            continue
        source = {"id": entry["id"], "name": entry["name"], "provider": "rss"}
        started = time.monotonic()
        try:
            raw_items = parse_feed(client.get(entry["url"]).text)
            max_items = int(entry.get("max_items", config.get("rss_default_max_items", 100)))
            raw_items = raw_items[:max(0, max_items)]
            floor = int(entry.get("source_floor", 55 if entry.get("trusted_ai") else 0))
            items = []
            for rank, raw in enumerate(raw_items, 1):
                item_source, duplicate_title, extra = source, raw["title"], {}
                if source["id"].startswith("google-news-") and raw.get("publisher"):
                    publisher = clean_text(raw["publisher"])
                    publisher_id = hashlib.sha1(publisher.lower().encode("utf-8")).hexdigest()[:10]
                    item_source = {"id": f"google-news:{publisher_id}", "name": publisher, "provider": "google_news_rss"}
                    duplicate_title = remove_publisher_suffix(raw["title"], publisher)
                    extra = {"feed_source_id": source["id"], "publisher": publisher}
                item = build_item(item_source, rank, raw["title"], raw["url"], raw["published_at"],
                                  snippet=raw["snippet"], external_id=raw["external_id"], source_floor=floor,
                                  extra=extra, duplicate_title=duplicate_title)
                if item["relevance_score"] >= min_score and within_lookback(item["published_at"], lookback_hours):
                    items.append(item)
            collected[source["id"]] = items
            statuses.append(source_status(source, "success", started, len(raw_items), len(items)))
            print(f"  {source['name']}: {len(raw_items)} 条，命中 {len(items)} 条")
        except Exception as exc:
            statuses.append(source_status(source, "failed", started, error=f"{type(exc).__name__}: {exc}"))
            print(f"  {source['name']}: 失败 - {type(exc).__name__}: {exc}")
    return collected, statuses


def collect_hackernews(client, config, min_score, lookback_hours):
    entry = config.get("hackernews", {})
    if not entry.get("enabled", True):
        return {}, []
    source = {"id": "hackernews-direct", "name": "Hacker News", "provider": "official_api"}
    started = time.monotonic()
    try:
        story_ids = client.get_json("https://hacker-news.firebaseio.com/v0/topstories.json")[:int(entry.get("max_items", 80))]

        def fetch_story(story_id):
            try:
                return client.get_json(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=8) as executor:
            stories = list(executor.map(fetch_story, story_ids))
        items = []
        for rank, raw in enumerate(stories, 1):
            if not raw or not raw.get("title") or raw.get("type") not in ("story", "job"):
                continue
            published_at = parse_datetime(raw.get("time"))
            url = raw.get("url") or f"https://news.ycombinator.com/item?id={raw.get('id')}"
            item = build_item(source, rank, raw["title"], url, published_at, external_id=raw.get("id"),
                              extra={"score": raw.get("score"), "comments": raw.get("descendants")})
            if item["relevance_score"] >= min_score and within_lookback(item["published_at"], lookback_hours):
                items.append(item)
        status = "partial" if any(story is None for story in stories) else "success"
        print(f"  {source['name']}: {len(story_ids)} 条，命中 {len(items)} 条 ({status})")
        return {source["id"]: items}, [source_status(source, status, started, len(story_ids), len(items))]
    except Exception as exc:
        print(f"  {source['name']}: 失败 - {type(exc).__name__}: {exc}")
        return {}, [source_status(source, "failed", started, error=f"{type(exc).__name__}: {exc}")]


def collect_arxiv(client, config, min_score, lookback_hours):
    entry = config.get("arxiv", {})
    if not entry.get("enabled", True):
        return {}, []
    source = {"id": "arxiv-ai", "name": "arXiv AI", "provider": "official_api"}
    started = time.monotonic()
    try:
        params = {"search_query": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:cs.CV OR cat:cs.RO", "start": 0,
                  "max_results": int(entry.get("max_items", 30)), "sortBy": "submittedDate", "sortOrder": "descending"}
        raw_items = parse_feed(client.get("https://export.arxiv.org/api/query", params=params).text)
        items = []
        for rank, raw in enumerate(raw_items, 1):
            item = build_item(source, rank, raw["title"], raw["url"], raw["published_at"], snippet=raw["snippet"],
                              external_id=raw["external_id"], source_floor=55)
            if item["relevance_score"] >= min_score and within_lookback(item["published_at"], lookback_hours):
                items.append(item)
        print(f"  {source['name']}: {len(raw_items)} 条，命中 {len(items)} 条")
        return {source["id"]: items}, [source_status(source, "success", started, len(raw_items), len(items))]
    except Exception as exc:
        print(f"  {source['name']}: 失败 - {type(exc).__name__}: {exc}")
        return {}, [source_status(source, "failed", started, error=f"{type(exc).__name__}: {exc}")]


def merge_source_maps(target, incoming):
    for source_id, items in incoming.items():
        target.setdefault(source_id, []).extend(items)


def _published_timestamp(value):
    try:
        return datetime.fromisoformat(value).timestamp() if value else 0
    except ValueError:
        return 0


def deduplicate_news(raw_by_source):
    records, url_index, title_index = [], {}, {}

    def find_record(item):
        if item.get("canonical_url") and item["canonical_url"] in url_index:
            return url_index[item["canonical_url"]], "exact_url"
        if item.get("duplicate_key") and item["duplicate_key"] in title_index:
            return title_index[item["duplicate_key"]], "exact_title"
        for index, record in enumerate(records):
            if titles_similar(item.get("duplicate_key", ""), record.get("duplicate_key", "")):
                return index, "similar_title"
        return None, "new"

    for items in raw_by_source.values():
        for item in items:
            record_index, method = find_record(item)
            source_detail = {key: item.get(key) for key in ("source_id", "source_name", "provider", "rank", "url", "published_at")}
            if record_index is None:
                record = dict(item)
                identity = item["duplicate_key"] or item["canonical_url"] or item["title"]
                record.update({"id": hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16], "sources": [source_detail],
                               "source_count": 1, "all_titles": [item["title"]], "dedup_methods": []})
                records.append(record)
                record_index = len(records) - 1
            else:
                record = records[record_index]
                merged_keywords = list(dict.fromkeys(record.get("matched_keywords", []) + item.get("matched_keywords", [])))
                source_identity = (source_detail["source_id"], canonicalize_url(source_detail.get("url", "")))
                existing = {(s["source_id"], canonicalize_url(s.get("url", ""))) for s in record["sources"]}
                if source_identity not in existing:
                    record["sources"].append(source_detail)
                record["source_count"] = len({s["source_id"] for s in record["sources"]})
                if item["title"] not in record["all_titles"]:
                    record["all_titles"].append(item["title"])
                if method not in record["dedup_methods"]:
                    record["dedup_methods"].append(method)
                if (item["relevance_score"], -item["rank"]) > (record["relevance_score"], -record["rank"]):
                    preserved = {key: record[key] for key in ("id", "sources", "source_count", "all_titles", "dedup_methods")}
                    record.update(item)
                    record.update(preserved)
                record["matched_keywords"] = merged_keywords
            record = records[record_index]
            if item.get("canonical_url"):
                url_index[item["canonical_url"]] = record_index
            if item.get("duplicate_key"):
                title_index[item["duplicate_key"]] = record_index

    for record in records:
        dates = [s["published_at"] for s in record["sources"] if s.get("published_at")]
        record["first_published_at"] = min(dates) if dates else record.get("published_at")
        record["latest_published_at"] = max(dates) if dates else record.get("published_at")
        record["best_rank"] = min((s["rank"] for s in record["sources"]), default=record.get("rank", 999))
    records.sort(key=lambda item: (-item["source_count"], -item["relevance_score"],
                                  -_published_timestamp(item.get("latest_published_at")), item["best_rank"]))
    return records


def write_atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    os.replace(temp_path, path)


def format_source_status(status):
    detail = f"{status['source_name']} [{status['provider']}]: {status['status']}"
    if status["status"] != "failed":
        detail += f"，读取 {status['total_items']}，命中 {status['matched_items']}"
    elif status.get("error"):
        detail += f"，{status['error']}"
    return detail


def format_markdown(items, meta, statuses):
    label = "早报" if meta["edition"] == "morning" else "晚报"
    lines = [f"# AI Daily 数据采集交接稿 - {label} - {meta['date']}", "", f"> 抓取时间：{meta['fetched_at']}",
             f"> 数据源：成功 {meta['source_summary']['successful']} / 尝试 {meta['source_summary']['attempted']}",
             f"> 原始命中：{meta['raw_total']} 条；去重后：{meta['deduped_total']} 条", ""]
    for index, item in enumerate(items, 1):
        title = f"[{item['title']}]({item['url']})" if item.get("url") else item["title"]
        sources = "、".join(source["source_name"] for source in item["sources"])
        lines.extend([f"{index}. {title}",
                      f"   - 相关性：{item['relevance_score']}/100（{item['confidence']}，{item['match_reason']}）",
                      f"   - 命中词：{'、'.join(item['matched_keywords']) or '垂直来源保留'}",
                      f"   - 来源：{sources}；发布时间：{item.get('latest_published_at') or '未知'}", ""])
    lines.extend(["## 数据源状态", ""])
    lines.extend(f"- {format_source_status(status)}" for status in statuses)
    return "\n".join(lines)


def format_txt(items, meta, statuses):
    label = "早报" if meta["edition"] == "morning" else "晚报"
    lines = [f"AI Daily 数据采集交接稿 - {label} - {meta['date']}", f"抓取时间：{meta['fetched_at']}",
             f"数据源：成功 {meta['source_summary']['successful']} / 尝试 {meta['source_summary']['attempted']}",
             f"原始命中：{meta['raw_total']} 条；去重后：{meta['deduped_total']} 条",
             f"时间范围：{meta['time_coverage']['earliest'] or '未知'} 至 {meta['time_coverage']['latest'] or '未知'}",
             "说明：本文件未截断 Top N，供后续负责人继续筛选。", "", "=" * 72, ""]
    for index, item in enumerate(items, 1):
        lines.extend([f"{index}. {item['title']}", f"   相关性：{item['relevance_score']}/100（{item['confidence']}）",
                      f"   命中原因：{item['match_reason']}", f"   命中词：{'、'.join(item['matched_keywords']) or '垂直来源保留'}",
                      f"   发布时间：{item.get('latest_published_at') or '未知'}", f"   来源数：{item['source_count']}"])
        if item.get("url"):
            lines.append(f"   主链接：{item['url']}")
        if item.get("snippet"):
            lines.append(f"   补充信息：{item['snippet']}")
        for source in item["sources"]:
            lines.append(f"   - {source['source_name']} / 排名 {source['rank']} / {source.get('url') or '无链接'}")
        lines.extend(["", "-" * 72, ""])
    lines.extend(["数据源状态", "=" * 72])
    lines.extend(format_source_status(status) for status in statuses)
    lines.append("")
    return "\n".join(lines)


def build_meta(args, config, statuses, raw_total, items):
    success_states = {"success", "cache", "partial"}
    dates = [item.get("latest_published_at") for item in items if item.get("latest_published_at")]
    return {
        "schema_version": SCHEMA_VERSION, "run_id": f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{os.getpid()}",
        "date": datetime.now().strftime("%Y-%m-%d"), "edition": args.edition, "fetched_at": iso_now(),
        "min_relevance_score": args.min_score, "lookback_hours": args.hours, "raw_total": raw_total,
        "deduped_total": len(items), "known_publish_time_count": len(dates),
        "time_coverage": {"earliest": min(dates) if dates else None, "latest": max(dates) if dates else None},
        "source_summary": {"attempted": len(statuses),
                           "successful": sum(1 for s in statuses if s["status"] in success_states),
                           "failed": sum(1 for s in statuses if s["status"] == "failed"),
                           "zero_match": sum(1 for s in statuses if s["status"] in success_states and s["matched_items"] == 0)},
        "newsnow_base_url": config.get("newsnow_base_url"),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="宽口径采集 AI 产业候选新闻")
    parser.add_argument("edition", nargs="?", choices=["morning", "evening"], default="morning")
    parser.add_argument("--config", help="自定义 sources.json 路径")
    parser.add_argument("--output-dir", help="覆盖输出根目录")
    parser.add_argument("--hours", type=int, help="仅保留最近 N 小时；0 表示不按时间删除")
    parser.add_argument("--min-score", type=int, help="相关性最低分")
    parser.add_argument("--no-newsnow", action="store_true", help="仅运行独立直连数据源")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    args.min_score = config["min_relevance_score"] if args.min_score is None else args.min_score
    args.hours = config.get("lookback_hours", 0) if args.hours is None else args.hours
    output_base = Path(args.output_dir).expanduser().resolve() if args.output_dir else DEFAULT_OUTPUT_BASE
    date_str, output_dir = datetime.now().strftime("%Y-%m-%d"), None
    output_dir = output_base / date_str
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        client = HttpClient(config.get("request_timeout_seconds", 20), config.get("request_retries", 3))
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2

    raw_by_source, statuses = {}, []
    print(f"=== AI Daily 数据采集 - {args.edition} ===")
    print(f"输出目录：{output_dir}\n最低相关性：{args.min_score}；时间过滤：{args.hours or '关闭'}")
    collectors = []
    if not args.no_newsnow:
        collectors.append(("NewsNow 聚合源", collect_newsnow))
    collectors.extend([("独立 RSS/Atom 源", collect_rss), ("Hacker News 官方 API", collect_hackernews), ("arXiv 官方 API", collect_arxiv)])
    for label, collector in collectors:
        print(f"\n[{label}]")
        source_items, source_statuses = collector(client, config, args.min_score, args.hours)
        merge_source_maps(raw_by_source, source_items)
        statuses.extend(source_statuses)

    successful = sum(1 for status in statuses if status["status"] in ("success", "cache", "partial"))
    if not statuses or successful == 0:
        print("所有数据源均失败，未覆盖旧输出。", file=sys.stderr)
        return 3
    raw_total = sum(len(items) for items in raw_by_source.values())
    items = deduplicate_news(raw_by_source)
    meta = build_meta(args, config, statuses, raw_total, items)
    payload = {"meta": meta, "source_statuses": statuses, "items": items, "raw_by_source": raw_by_source}
    prefix = f"{date_str}_{args.edition}"
    paths = {"JSON": output_dir / f"{prefix}.json", "Markdown": output_dir / f"{prefix}.md", "TXT": output_dir / f"{prefix}.txt"}
    write_atomic(paths["JSON"], json.dumps(payload, ensure_ascii=False, indent=2))
    write_atomic(paths["Markdown"], format_markdown(items, meta, statuses))
    write_atomic(paths["TXT"], format_txt(items, meta, statuses))
    for label, path in paths.items():
        print(f"{label}: {path}")
    print(f"数据源成功 {meta['source_summary']['successful']}/{meta['source_summary']['attempted']}，原始命中 {raw_total} 条，去重后 {len(items)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
