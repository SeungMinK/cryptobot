"""업비트 공지사항 수집."""

import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

UPBIT_NOTICE_URL = "https://api-manager.upbit.com/api/v1/notices"


def fetch_upbit_notices(limit: int = 20) -> list[dict]:
    """업비트 공지사항 조회.

    상장/폐지/점검 등 매매에 영향 주는 공지 수집.
    """
    try:
        response = requests.get(
            UPBIT_NOTICE_URL,
            params={"page": 1, "per_page": limit, "thread_name": "general"},
            timeout=10,
            headers={"User-Agent": "CryptoBot/1.0"},
        )
        response.raise_for_status()
        data = response.json()

        articles = []
        for item in data.get("data", {}).get("list", []):
            title = item.get("title", "")
            created = item.get("created_at", "")

            # 카테고리 판단
            category = "listing"
            title_lower = title.lower()
            if any(w in title_lower for w in ["점검", "maintenance", "중단"]):
                category = "maintenance"
            elif any(w in title_lower for w in ["상장", "listing", "마켓 추가"]):
                category = "listing"
            elif any(w in title_lower for w in ["폐지", "delist", "거래 지원 종료"]):
                category = "delisting"

            articles.append({
                "source": "upbit",
                "title": title,
                "summary": title,  # 공지는 제목이 곧 요약
                "url": f"https://upbit.com/service_center/notice?id={item.get('id', '')}",
                "published_at": created[:19].replace("T", " ") if created else None,
                "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "category": category,
                "coins_mentioned": "",
                "sentiment_keyword": "neutral",
            })

        logger.info("업비트 공지: %d건 수집", len(articles))
        return articles

    except Exception as e:
        logger.error("업비트 공지 수집 실패: %s", e)
        return []
