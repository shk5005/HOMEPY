"""Slack webhook notifier."""
from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class SlackNotifier:
    def __init__(self, webhook_url: str, timeout: float = 5.0, max_retries: int = 2):
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.max_retries = max_retries

    async def send(self, title: str, body: str) -> bool:
        payload = {"text": f"*{title}*\n{body}"}
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(self.webhook_url, json=payload)
                    if resp.status_code < 300:
                        return True
                    logger.warning("Slack returned status %s", resp.status_code)
            except Exception as exc:  # never raise on channel failure
                logger.warning("Slack send failed: %s", exc)
            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2**attempt))
        return False
