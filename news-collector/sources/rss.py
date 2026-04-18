"""RSS 뉴스 수집 — CoinDesk, CoinTelegraph."""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    {
        "name": "coindesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "category_default": "market",
    },
    {
        "name": "cointelegraph",
        "url": "https://cointelegraph.com/rss",
        "category_default": "market",
    },
]

# 코인 키워드 → 티커 매핑
COIN_KEYWORDS = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "eth": "ETH",
    "ether": "ETH",
    "xrp": "XRP",
    "ripple": "XRP",
    "solana": "SOL",
    "sol": "SOL",
    "dogecoin": "DOGE",
    "doge": "DOGE",
    "cardano": "ADA",
    "ada": "ADA",
    "trump": "TRUMP",
    "tao": "TAO",
    "bittensor": "TAO",
}

# 감성 키워드
POSITIVE_KEYWORDS = ["surge", "rally", "bull", "gain", "soar", "rise", "jump", "breakout", "approval", "adopt"]
NEGATIVE_KEYWORDS = ["crash", "drop", "fall", "bear", "plunge", "hack", "ban", "fraud", "lawsuit", "dump", "fear"]


def extract_coins(text: str) -> str:
    """텍스트에서 코인 티커 추출."""
    text_lower = text.lower()
    found = set()
    for keyword, ticker in COIN_KEYWORDS.items():
        if keyword in text_lower:
            found.add(ticker)
    return ",".join(sorted(found)) if found else ""


def detect_sentiment(text: str) -> str:
    """키워드 기반 감성 분류."""
    text_lower = text.lower()
    pos = sum(1 for w in POSITIVE_KEYWORDS if w in text_lower)
    neg = sum(1 for w in NEGATIVE_KEYWORDS if w in text_lower)
    if pos > neg:
        return "positive"
    elif neg > pos:
        return "negative"
    return "neutral"


def categorize(text: str) -> str:
    """뉴스 카테고리 분류."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["regulation", "sec", "law", "ban", "legal", "court"]):
        return "regulation"
    if any(w in text_lower for w in ["hack", "exploit", "vulnerability", "security"]):
        return "security"
    if any(w in text_lower for w in ["listing", "delist", "launch", "airdrop"]):
        return "listing"
    if any(w in text_lower for w in ["technology", "upgrade", "fork", "layer", "protocol"]):
        return "technology"
    return "market"


def fetch_rss(feed: dict) -> list[dict]:
    """RSS 피드에서 뉴스 가져오기."""
    try:
        response = requests.get(feed["url"], timeout=15, headers={"User-Agent": "CryptoBot/1.0"})
        response.raise_for_status()

        root = ET.fromstring(response.content)
        articles = []

        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            if not title:
                continue

            link = item.findtext("link", "")
            description = item.findtext("description", "")
            pub_date = item.findtext("pubDate", "")

            # 요약: description에서 HTML 제거 + 3문장 제한
            summary = description
            if "<" in summary:
                import re

                summary = re.sub(r"<[^>]+>", "", summary)
            summary = summary.strip()[:500]

            # 발행시간 파싱
            published_at = None
            if pub_date:
                try:
                    from email.utils import parsedate_to_datetime

                    published_at = parsedate_to_datetime(pub_date).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

            combined_text = f"{title} {summary}"
            articles.append(
                {
                    "source": feed["name"],
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "published_at": published_at,
                    "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    "category": categorize(combined_text),
                    "coins_mentioned": extract_coins(combined_text),
                    "sentiment_keyword": detect_sentiment(combined_text),
                }
            )

        logger.info("%s: %d건 수집", feed["name"], len(articles))
        return articles

    except Exception as e:
        logger.error("%s RSS 수집 실패: %s", feed["name"], e)
        return []


def fetch_all_rss() -> list[dict]:
    """모든 RSS 피드에서 뉴스 수집."""
    all_articles = []
    for feed in RSS_FEEDS:
        articles = fetch_rss(feed)
        all_articles.extend(articles)
    return all_articles
