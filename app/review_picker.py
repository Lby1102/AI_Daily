"""终端选择 review 内实际上传的 HTML 文件。"""
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup


def choose_article(review_root: Path) -> Path | None:
    root = review_root.resolve()
    files = sorted((p for p in root.rglob("*")
                    if p.is_file() and p.suffix.lower() in (".html", ".htm")
                    and p.resolve().is_relative_to(root)),
                   key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)
    if not files:
        print(f"没有可上传的 HTML 稿件：{root}")
        return None
    print("\n请选择要上传到公众号草稿箱的稿件（上传 HTML，Word 用于审核）：")
    fixed_cover = root.parent / "data" / "wechat-cover" / "cover.jpg"
    for index, path in enumerate(files, 1):
        soup = BeautifulSoup(path.read_text(encoding="utf-8-sig"), "html.parser")
        title = soup.find("h1") or soup.title
        label = " ".join(title.get_text(" ", strip=True).split()) if title else "无标题"
        modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%m-%d %H:%M")
        print(f"[{index}] {path.relative_to(root)} | 修改于 {modified}")
        print(f"    {label[:100]} | 固定封面：{fixed_cover.name if fixed_cover.is_file() else '缺失'}")
    print("[0] 取消，返回菜单")
    while True:
        try:
            answer = input("输入稿件编号：").strip()
        except EOFError:
            return None
        if answer == "0":
            return None
        if answer.isdecimal() and 1 <= int(answer) <= len(files):
            selected = files[int(answer) - 1]
            print(f"\n本次上传文件：{selected}")
            return selected
        print(f"请输入 1～{len(files)}，或输入 0 取消。")
