"""KakaoTalk notifier."""
from __future__ import annotations

import asyncio
import json
import logging

import httpx

logger = logging.getLogger(__name__)

KAKAO_API_URL = "https://kapi.kakao.com/v2/api/talk/memo/send"


class KakaoNotifier:
    def __init__(
        self,
        api_key: str,
        template_id: str,
        timeout: float = 5.0,
        max_retries: int = 2,
    ):
        self.api_key = api_key
        self.template_id = template_id
        self.timeout = timeout
        self.max_retries = max_retries

    async def send(self, title: str, body: str) -> bool:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {
            "template_id": self.template_id,
            "template_args": json.dumps({"title": title, "body": body}, ensure_ascii=False),
        }
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(KAKAO_API_URL, headers=headers, data=data)
                    if resp.status_code < 300:
                        return True
                    logger.warning("Kakao returned status %s", resp.status_code)
            except Exception as exc:
                logger.warning("Kakao send failed: %s", exc)
            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2**attempt))
        return False
