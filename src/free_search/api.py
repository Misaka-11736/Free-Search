"""Explicit, session-only consent for optional remote result reranking.

Indexing and embeddings stay local. Only bounded text snippets are sent.
"""

from __future__ import annotations

import hashlib
import ipaddress
import math
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit


class ApiError(RuntimeError):
    """A safe user-facing API failure, without response bodies or credentials."""


@dataclass(frozen=True)
class ApiConfig:
    endpoint: str
    model: str
    request_limit: int = 100
    byte_limit: int = 10 * 1024 * 1024
    max_candidates: int = 20
    snippet_chars: int = 2000

    def __post_init__(self):
        url = urlsplit(self.endpoint)
        try:
            loopback = ipaddress.ip_address(url.hostname or "").is_loopback
        except ValueError:
            loopback = url.hostname == "localhost"
        if (
            not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or (url.scheme != "https" and not (url.scheme == "http" and loopback))
        ):
            raise ValueError("API 地址须为 HTTPS；仅本机回环地址允许 HTTP，地址中不能包含密钥。")
        if not self.model.strip():
            raise ValueError("请填写服务商的重排模型名称。")
        if min(self.request_limit, self.byte_limit, self.max_candidates, self.snippet_chars) < 1:
            raise ValueError("API 用量限制必须大于零。")

    @property
    def credential_id(self) -> str:
        return hashlib.sha256(self.endpoint.rstrip("/").encode()).hexdigest()


@dataclass(frozen=True)
class Consent:
    text: bool = False
    images: bool = False
    audio_video: bool = False
    roots: tuple[str, ...] = ()

    def permits(self, candidate: dict) -> bool:
        if not self.text or not candidate.get("path"):
            return False
        path = Path(candidate["path"]).resolve()
        if not any(path.is_relative_to(Path(root).resolve()) for root in self.roots):
            return False
        suffix = path.suffix.lower()
        if suffix in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wma",
                      ".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".m4v"}:
            return self.audio_video
        modality = str(candidate.get("modality", "text")).lower()
        if modality in {"image", "ocr", "image_ocr", "visual"}:
            return self.images
        if modality in {"audio", "video", "speech", "transcript", "video_frame", "frame"}:
            return self.audio_video
        # Inspect the source extension as well as the chunk label: OCR and ASR
        # chunks may be described as text by an extractor.
        suffix = path.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".gif"}:
            return self.images
        if suffix in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".mp4", ".mov", ".mkv", ".avi", ".webm"}:
            return self.audio_video
        return modality in {"text", "document", "code", "pdf", "office", "metadata"}


def save_key(config: ApiConfig, key: str) -> None:
    import keyring

    keyring.set_password("FreeSearch", config.credential_id, key)


def load_key(config: ApiConfig) -> str:
    import keyring

    return keyring.get_password("FreeSearch", config.credential_id) or ""


class ApiClient:
    """Cohere/SiliconFlow-style POST /rerank adapter with no automatic retry.

    Failed requests consume the session budget too, since a provider may have
    processed a request even when the response never reached this client.
    """

    def __init__(self, config: ApiConfig, consent: Consent, *, edition: str,
                 key: str = "", transport=None):
        if edition != "api":
            raise ApiError("完全离线版禁止使用远程 API。")
        self.config = config
        self.consent = consent
        self.key = key
        self._transport = transport
        self.requests = 0
        self.bytes_sent = 0
        self._lock = Lock()

    def rerank(self, query: str, candidates: list[dict], query_source: dict | None = None) -> list[dict]:
        import json
        import httpx

        if not self.consent.text:
            raise ApiError("尚未授权文本外发。")
        if query_source is not None and not self.consent.permits(query_source):
            raise ApiError("本次查询的来源类型或目录未获外发授权。请补充授权，或点击“恢复本地”后重试。")
        if len(query) > 4000:
            raise ApiError("API 查询长度最多 4000 字符。")
        approved = [
            (index, item) for index, item in enumerate(candidates)
            if self.consent.permits(item) and str(item.get("text", "")).strip()
        ][:self.config.max_candidates]
        if not approved:
            return candidates
        payload = {
            "model": self.config.model,
            "query": query,
            "documents": [str(item["text"])[:self.config.snippet_chars] for _, item in approved],
            "top_n": len(approved),
            "return_documents": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with self._lock:
            if self.requests >= self.config.request_limit or self.bytes_sent + len(body) > self.config.byte_limit:
                raise ApiError("本次会话 API 用量已达上限；请重新检查用量限制。")
            self.requests += 1
            self.bytes_sent += len(body)
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        try:
            with httpx.Client(
                timeout=30, follow_redirects=False, trust_env=False, transport=self._transport,
            ) as client:
                response = client.post(
                    self.config.endpoint.rstrip("/") + "/rerank", content=body, headers=headers,
                )
                if response.status_code != 200:
                    raise ApiError(f"重排服务返回 HTTP {response.status_code}；本地索引仍可使用。")
                data = response.json()
        except httpx.HTTPError as exc:
            raise ApiError("重排服务连接失败或超时，请检查地址和网络。") from None
        except ValueError:
            raise ApiError("重排服务未返回有效 JSON。") from None
        try:
            ranked = data["results"]
            indices = [row["index"] for row in ranked]
            if (len(indices) != len(approved) or any(type(i) is not int for i in indices)
                    or sorted(indices) != list(range(len(approved)))):
                raise ValueError("invalid indices")
            for row in ranked:
                if not math.isfinite(float(row["relevance_score"])):
                    raise ValueError("invalid score")
            ranked = sorted(ranked, key=lambda row: float(row["relevance_score"]), reverse=True)
        except (KeyError, TypeError, ValueError):
            raise ApiError("重排响应缺少完整、不重复的候选编号或有效分数。") from None
        # Replace only eligible positions. A service never receives or overrides
        # the relative placement of results whose source was not authorized.
        output = list(candidates)
        for (position, _), row in zip(approved, ranked):
            item = dict(approved[row["index"]][1])
            item["api_score"] = float(row["relevance_score"])
            output[position] = item
        return output
