"""
Slack resource for Dagster notifications.
"""
import json
import logging
import os
from typing import List, Optional

import requests
from dagster import ConfigurableResource

logger = logging.getLogger(__name__)


class SlackResource(ConfigurableResource):
    webhook_url: str = ""
    channel: Optional[str] = None
    username: str = "Pet Trends Bot"
    icon_emoji: str = ":dog:"

    @classmethod
    def daily_pulse_from_env(cls) -> "SlackResource":
        return cls(webhook_url=os.getenv("SLACK_DAILY_PULSE_WEBHOOK", ""))

    @classmethod
    def weekly_digest_from_env(cls) -> "SlackResource":
        return cls(webhook_url=os.getenv("SLACK_WEEKLY_DIGEST_WEBHOOK", ""))

    def send_message(self, text: str, blocks: Optional[list] = None) -> bool:
        if not self.webhook_url:
            logger.warning("Slack webhook URL not configured — skipping send")
            return False

        payload: dict = {
            "text": text,
            "username": self.username,
            "icon_emoji": self.icon_emoji,
        }
        if self.channel:
            payload["channel"] = self.channel
        if blocks:
            payload["blocks"] = blocks

        try:
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            response.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Failed to send Slack message: %s", exc)
            return False

    def send_blocks(self, blocks: List[dict], text: str = "Pet Trends Update") -> bool:
        return self.send_message(text=text, blocks=blocks)
