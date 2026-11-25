"""SMTP email notifier."""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


class EmailNotifier:
    def __init__(
        self,
        smtp_host: str,
        from_addr: str,
        to_addrs: list[str],
        timeout: float = 5.0,
        max_retries: int = 2,
    ):
        self.smtp_host = smtp_host
        self.from_addr = from_addr
        self.to_addrs = list(to_addrs)
        self.timeout = timeout
        self.max_retries = max_retries

    def _send_sync(self, title: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)
        msg.set_content(body)
        with smtplib.SMTP(self.smtp_host, timeout=self.timeout) as smtp:
            smtp.send_message(msg)

    async def send(self, title: str, body: str) -> bool:
        for attempt in range(self.max_retries + 1):
            try:
                await asyncio.to_thread(self._send_sync, title, body)
                return True
            except Exception as exc:
                logger.warning("Email send failed: %s", exc)
            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2**attempt))
        return False
