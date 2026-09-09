from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import Any

import requests


API_BASE = "https://api.weixin.qq.com"


class WeChatAPIError(RuntimeError):
    pass


class WeChatAPI:
    def __init__(self, app_id: str, app_secret: str, timeout: int = 30) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.timeout = timeout
        self.session = requests.Session()
        self._access_token: str | None = None

    def get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        response = self.session.post(
            f"{API_BASE}/cgi-bin/stable_token",
            json={
                "grant_type": "client_credential",
                "appid": self.app_id,
                "secret": self.app_secret,
                "force_refresh": False,
            },
            timeout=self.timeout,
        )
        data = self._json_or_raise(response)
        token = data.get("access_token")
        if not token:
            raise WeChatAPIError(f"微信未返回 access_token: {data}")
        self._access_token = str(token)
        return self._access_token

    def upload_content_image(
        self, content: bytes, filename: str, content_type: str | None = None
    ) -> str:
        content_type = content_type or mimetypes.guess_type(filename)[0] or "image/jpeg"
        response = self.session.post(
            f"{API_BASE}/cgi-bin/media/uploadimg",
            params={"access_token": self.get_access_token()},
            files={"media": (filename, content, content_type)},
            timeout=self.timeout,
        )
        data = self._json_or_raise(response)
        url = data.get("url")
        if not url:
            raise WeChatAPIError(f"正文图片上传成功但未返回 URL: {data}")
        return str(url)

    def upload_permanent_thumb(self, image_path: Path) -> str:
        content_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        with image_path.open("rb") as image:
            response = self.session.post(
                f"{API_BASE}/cgi-bin/material/add_material",
                params={"access_token": self.get_access_token(), "type": "thumb"},
                files={"media": (image_path.name, image, content_type)},
                timeout=self.timeout,
            )
        data = self._json_or_raise(response)
        media_id = data.get("media_id")
        if not media_id:
            raise WeChatAPIError(f"封面上传成功但未返回 media_id: {data}")
        return str(media_id)

    def add_draft(self, article: dict[str, Any]) -> str:
        # 微信草稿接口会把 requests 的默认 ASCII JSON 转义（如 \u4e2d）
        # 原样显示在编辑器中。必须明确发送未转义的 UTF-8 JSON。
        payload = json.dumps(
            {"articles": [article]}, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        response = self.session.post(
            f"{API_BASE}/cgi-bin/draft/add",
            params={"access_token": self.get_access_token()},
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=self.timeout,
        )
        data = self._json_or_raise(response)
        media_id = data.get("media_id")
        if not media_id:
            raise WeChatAPIError(f"创建草稿成功但未返回 media_id: {data}")
        return str(media_id)

    @staticmethod
    def _json_or_raise(response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise WeChatAPIError(
                f"微信接口返回了非 JSON 内容，HTTP {response.status_code}"
            ) from exc

        if not response.ok:
            raise WeChatAPIError(f"微信接口 HTTP {response.status_code}: {data}")
        errcode = data.get("errcode")
        if str(errcode) == "40164":
            match = re.search(r"invalid ip\s+([^\s,]+)", str(data.get("errmsg", "")))
            ip = match.group(1) if match else "微信错误信息中的出口 IP"
            raise WeChatAPIError(
                f"微信拒绝访问（40164）：出口 IP {ip} 不在公众号 IP 白名单。\n"
                f"请公众号管理员在后台的开发配置中找到 IP 白名单，添加 {ip}，保留已有条目并保存。\n"
                "保存后重新选择同一稿件上传即可，无需重新生成。网络或代理改变后，出口 IP 也可能变化。"
            )
        if errcode not in (None, 0):
            raise WeChatAPIError(
                f"微信接口错误 {errcode}: {data.get('errmsg', '未知错误')}"
            )
        return data
