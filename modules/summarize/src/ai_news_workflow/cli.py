from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Settings
from .deepseek_client import DeepSeekClient
from .pipeline import run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从原始 TXT 生成 5 条 AI 资讯 HTML")
    parser.add_argument("--raw", type=Path, default=PROJECT_ROOT / "input/raw_news.txt")
    parser.add_argument("--feedback", type=Path, default=PROJECT_ROOT / "input/feedback.txt")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "output/article.html")
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "output/scoring_report.json")
    parser.add_argument("--template", type=Path, default=PROJECT_ROOT / "templates/article.html")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        settings = Settings.load(PROJECT_ROOT / ".env")
        ranking = run_pipeline(
            client=DeepSeekClient(settings),
            raw_path=args.raw,
            feedback_path=args.feedback,
            output_path=args.output,
            report_path=args.report,
            template_path=args.template,
            max_input_chars=settings.max_input_chars,
        )
    except Exception as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    print(f"已生成 HTML：{args.output}")
    print(f"评分报告：{args.report}")
    for index, item in enumerate(ranking.selected, start=1):
        print(f"{index}. {item.title}（{item.total_score:.2f} 分）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
