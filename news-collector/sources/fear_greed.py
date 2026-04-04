"""Fear & Greed Index 수집."""

import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"


def fetch_fear_greed() -> dict | None:
    """Fear & Greed Index 조회.

    Returns:
        {"value": 25, "classification": "Extreme Fear", ...} 또는 None
    """
    try:
        response = requests.get(FEAR_GREED_URL, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data.get("data"):
            return None

        entry = data["data"][0]
        result = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "value": int(entry["value"]),
            "classification": entry["value_classification"],
            "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }

        logger.info("Fear & Greed Index: %d (%s)", result["value"], result["classification"])
        return result

    except Exception as e:
        logger.error("Fear & Greed 조회 실패: %s", e)
        return None
