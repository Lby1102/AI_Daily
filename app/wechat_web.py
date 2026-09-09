"""通过本机 Chrome 的公众号网页创建草稿，不调用微信开放 API。"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import BrowserContext, Page, sync_playwright

from app.config import Settings


MP_HOME = "https://mp.weixin.qq.com/"
IMAGE_MARKER = "__AIDAILY_IMAGE_{:04d}__"


@dataclass(frozen=True)
class PreparedArticle:
    title: str
    digest: str
    html: str
    images: tuple[tuple[str, Path], ...]


def prepare_article(article_html: Path) -> PreparedArticle:
    """提取稿件并转换成适合粘贴到公众号编辑器的内联样式 HTML。"""
    article_html = article_html.resolve()
    soup = BeautifulSoup(article_html.read_text(encoding="utf-8-sig"), "html.parser")
    meta = soup.find("meta", attrs={"name": "wechat:title"})
    title = (meta.get("content", "").strip() if meta else "")
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else "AI 资讯"
    title = title[:64]

    intro = soup.select_one(".introduction")
    digest = (intro.get_text(" ", strip=True) if intro else "")[:120]
    content = soup.select_one("main") or soup.body or soup
    for node in list(content.select("h1")):
        node.decompose()

    images: list[tuple[str, Path]] = []
    for index, image in enumerate(list(content.find_all("img")), 1):
        src = str(image.get("src", "")).strip()
        path = (article_html.parent / src).resolve()
        if not src or not path.is_file():
            image.decompose()
            continue
        marker = IMAGE_MARKER.format(index)
        placeholder = soup.new_tag("p")
        placeholder.string = marker
        image.replace_with(placeholder)
        images.append((marker, path))

    styles = {
        "header": "padding-bottom:20px;border-bottom:1px solid #e8ebf1;",
        "h2": "margin:28px 0 14px;font-size:22px;line-height:1.5;color:#18212f;font-weight:700;",
        "p": "margin:10px 0;line-height:1.8;color:#303c50;font-size:16px;",
        "footer": "margin-top:24px;color:#687386;font-size:13px;text-align:center;",
    }
    class_styles = {
        "meta": "color:#687386;font-size:14px;",
        "introduction": "margin:18px 0;color:#3d4858;font-size:17px;line-height:1.8;",
        "feature-article": "padding:26px 0;border-bottom:1px solid #e8ebf1;",
        "section-label": "color:#315efb;font-size:13px;font-weight:700;letter-spacing:2px;",
        "article-lead": "padding:16px 18px;background:#f3f6ff;border-left:3px solid #315efb;color:#303c50;font-size:16px;",
        "source": "margin-top:20px;padding-top:12px;border-top:1px dashed #e8ebf1;color:#687386;font-size:14px;",
        "conclusion": "margin-top:28px;padding:20px 22px;background:#f7f8fa;",
    }
    for node in content.find_all(True):
        if not isinstance(node, Tag):
            continue
        parts = [styles.get(node.name, "")]
        for cls in node.get("class", []):
            parts.append(class_styles.get(cls, ""))
        existing = str(node.get("style", ""))
        if existing:
            parts.append(existing)
        attrs = {key: value for key, value in node.attrs.items()
                 if key in {"href", "target", "rel"}}
        merged = "".join(parts)
        if merged:
            attrs["style"] = merged
        node.attrs = attrs

    html = "".join(str(child) for child in content.contents).strip()
    return PreparedArticle(title=title, digest=digest, html=html, images=tuple(images))


def _open_context(settings: Settings):
    runtime = sync_playwright().start()
    profile = settings.data_dir / "wechat-browser-profile"
    profile.mkdir(parents=True, exist_ok=True)
    context = runtime.chromium.launch_persistent_context(
        str(profile), channel="chrome", headless=False,
        viewport={"width": 1440, "height": 900}, locale="zh-CN",
        args=["--disable-blink-features=AutomationControlled"],
    )
    return runtime, context


def _page(context: BrowserContext) -> Page:
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(MP_HOME, wait_until="domcontentloaded", timeout=60_000)
    return page


def _logged_in(page: Page) -> bool:
    return "token=" in page.url and "cgi-bin" in page.url


def login(timeout_seconds: int = 600) -> int:
    settings = Settings()
    runtime, context = _open_context(settings)
    try:
        page = _page(context)
        if _logged_in(page):
            print("公众号网页登录状态有效。")
            return 0
        print("已打开项目专用 Chrome。请扫码登录公众号；登录状态会保存在本机。")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            page.wait_for_timeout(1_000)
            if _logged_in(page):
                print("公众号网页登录成功。")
                return 0
        print("等待登录超时，请重新运行。", file=sys.stderr)
        return 1
    finally:
        context.close()
        runtime.stop()


def _open_editor(page: Page, context: BrowserContext) -> Page:
    old_pages = set(context.pages)
    page.locator(".new-creation__menu-content").filter(has_text="文章").first.click(force=True)
    page.wait_for_timeout(4_000)
    created = [item for item in context.pages if item not in old_pages]
    editor = created[-1] if created else page
    editor.wait_for_load_state("domcontentloaded")
    editor.locator('.ProseMirror:visible:not([data-placeholder])').last.wait_for(timeout=30_000)
    return editor


def _paste_body(page: Page, body, prepared: PreparedArticle) -> None:
    body.click()
    plain = BeautifulSoup(prepared.html, "html.parser").get_text("\n", strip=True)
    page.evaluate("""([el, html, plain]) => {
      const data = new DataTransfer();
      data.setData('text/html', html);
      data.setData('text/plain', plain);
      el.dispatchEvent(new ClipboardEvent('paste', {
        clipboardData:data, bubbles:true, cancelable:true
      }));
    }""", [body.element_handle(), prepared.html, plain])


def _select_marker(page: Page, body, marker: str, whole: bool) -> bool:
    return bool(page.evaluate("""([el, marker, whole]) => {
      const walker=document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let node;
      while(node=walker.nextNode()) {
        const start=node.data.indexOf(marker);
        if(start >= 0) {
          const range=document.createRange();
          range.setStart(node,start);
          range.setEnd(node,whole ? start+marker.length : start);
          const sel=getSelection(); sel.removeAllRanges(); sel.addRange(range);
          return true;
        }
      }
      return false;
    }""", [body.element_handle(), marker, whole]))


def _upload_images(page: Page, body, images: tuple[tuple[str, Path], ...]) -> None:
    for number, (marker, path) in enumerate(images, 1):
        if not _select_marker(page, body, marker, False):
            raise RuntimeError(f"正文图片占位符丢失：{path.name}")
        before = body.locator("img.rich_pages, img.js_insertlocalimg").count()
        page.locator('input[type="file"]').first.set_input_files(str(path))
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            page.wait_for_timeout(500)
            if body.locator("img.rich_pages, img.js_insertlocalimg").count() > before:
                break
        else:
            raise RuntimeError(f"正文图片上传超时：{path.name}")
        if _select_marker(page, body, marker, True):
            page.keyboard.press("Backspace")
        print(f"  正文图片 {number}/{len(images)}：{path.name}")


def _set_fixed_cover(page: Page, cover_path: Path) -> None:
    page.get_by_text("拖拽或选择封面", exact=True).click(force=True)
    page.locator('a:visible').filter(has_text="从图片库选择").first.click(force=True)
    page.wait_for_timeout(1_500)
    dialog = page.locator(".weui-desktop-dialog:visible").last
    file_inputs = dialog.locator('input[type="file"]')
    if not file_inputs.count():
        buttons = dialog.locator("button:visible, a:visible").all_inner_texts()
        raise RuntimeError(f"封面图片库未找到上传控件；当前按钮={buttons}；窗口={dialog.inner_text()[:1500]}")
    file_inputs.first.set_input_files(str(cover_path))
    page.wait_for_timeout(5_000)
    named = dialog.get_by_text(cover_path.name, exact=True).first
    item = named.locator("xpath=parent::div")
    if "selected" not in (item.get_attribute("class") or ""):
        item.click(force=True)
    dialog.get_by_role("button", name="下一步").click()
    finish = page.get_by_role("button", name="确认", exact=True)
    try:
        finish.first.wait_for(state="visible", timeout=30_000)
    except Exception as exc:
        active = page.locator(".weui-desktop-dialog:visible").last
        buttons = active.locator("button:visible").all_inner_texts()
        text = active.inner_text()[:1500]
        raise RuntimeError(f"封面裁剪窗口未出现确认按钮；当前按钮={buttons}；窗口={text}") from exc
    finish.first.click()
    page.locator(".weui-desktop-dialog:visible").last.wait_for(state="hidden", timeout=30_000)


def push(article_html: Path, *, save_draft: bool = True) -> str:
    prepared = prepare_article(article_html)
    settings = Settings()
    cover_path = settings.data_dir / "wechat-cover" / "cover.jpg"
    if not cover_path.is_file():
        raise RuntimeError(f"固定封面不存在：{cover_path}")
    runtime, context = _open_context(settings)
    try:
        home = _page(context)
        if not _logged_in(home):
            print("公众号登录已失效，请在打开的窗口扫码登录。")
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline and not _logged_in(home):
                home.wait_for_timeout(1_000)
            if not _logged_in(home):
                raise RuntimeError("等待公众号扫码登录超时。")
        page = _open_editor(home, context)
        title = page.locator('.ProseMirror:visible[data-placeholder="请在这里输入标题"]').first
        title.fill(prepared.title)
        body = page.locator('.ProseMirror:visible:not([data-placeholder])').last
        _paste_body(page, body, prepared)
        page.wait_for_timeout(800)
        _upload_images(page, body, prepared.images)
        if prepared.digest:
            page.locator("textarea.js_desc").fill(prepared.digest)
        _set_fixed_cover(page, cover_path)
        if not save_draft:
            print("试运行完成（未保存草稿）。")
            return prepared.title
        save = page.get_by_text("保存为草稿", exact=True).locator("xpath=ancestor::button[1]")
        save.click()
        page.wait_for_timeout(7_000)
        if "保存失败" in page.locator("body").inner_text():
            raise RuntimeError("公众号页面提示保存失败，请查看已打开的浏览器窗口。")
        print(f"草稿已保存：{prepared.title}")
        return prepared.title
    finally:
        context.close()
        runtime.stop()


def verify_draft(title: str, contains: str = "") -> bool:
    settings = Settings()
    runtime, context = _open_context(settings)
    try:
        page = _page(context)
        if not _logged_in(page):
            raise RuntimeError("公众号登录已失效。")
        old_pages = set(context.pages)
        page.get_by_text("全部草稿", exact=True).first.click(force=True)
        page.wait_for_timeout(5_000)
        created = [item for item in context.pages if item not in old_pages]
        drafts = created[-1] if created else page
        drafts.wait_for_load_state("domcontentloaded")
        normalize = lambda value: " ".join(value.replace("\u00a0", " ").split())
        found = normalize(title) in normalize(drafts.locator("body").inner_text())
        print("草稿箱验证：", "已找到" if found else "未找到", title)
        if not found:
            print("验证页面：", drafts.url)
            print(drafts.locator("body").inner_text()[:6000])
            return False
        if contains:
            old_pages = set(context.pages)
            title_node = drafts.get_by_text(title, exact=False).first
            title_node.click(force=True)
            drafts.wait_for_timeout(5_000)
            created = [item for item in context.pages if item not in old_pages]
            editor = created[-1] if created else drafts
            rich_body = editor.locator('.ProseMirror:visible:not([data-placeholder])')
            content = (rich_body.last.inner_text() if rich_body.count()
                       else editor.locator("body").inner_text())
            body_ok = contains in content and "\\u" not in content
            print("草稿正文验证：", "中文正常" if body_ok else "未通过")
            return body_ok
        return True
    finally:
        context.close()
        runtime.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本地浏览器上传公众号草稿")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login")
    push_parser = sub.add_parser("push")
    push_parser.add_argument("article", type=Path)
    push_parser.add_argument("--dry-run", action="store_true")
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("title")
    verify_parser.add_argument("--contains", default="")
    args = parser.parse_args(argv)
    if args.command == "login":
        return login()
    try:
        if args.command == "verify":
            return 0 if verify_draft(args.title, args.contains) else 1
        push(args.article, save_draft=not args.dry_run)
        return 0
    except Exception as exc:
        print(f"网页上传失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
