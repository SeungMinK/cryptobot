"""뉴스 수집기 메인.

30분 주기로 RSS 뉴스 + 업비트 공지 + Fear & Greed Index를 수집하여 DB에 저장.

사용법:
    python news-collector/collector.py
"""

import logging
import signal
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sources.fear_greed import fetch_fear_greed
from sources.rss import fetch_all_rss
from sources.upbit_notice import fetch_upbit_notices

logger = logging.getLogger(__name__)

# DB 경로
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cryptobot.db"


def get_db() -> sqlite3.Connection:
    """DB 연결."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def save_articles(articles: list[dict]) -> int:
    """뉴스 기사를 DB에 저장 (중복 제거)."""
    conn = get_db()
    saved = 0
    for a in articles:
        # URL 기반 중복 체크
        existing = conn.execute(
            "SELECT 1 FROM news_articles WHERE url = ? AND source = ?",
            (a["url"], a["source"]),
        ).fetchone()
        if existing:
            continue

        conn.execute(
            """INSERT INTO news_articles
            (source, title, summary, url, published_at, collected_at, category, coins_mentioned, sentiment_keyword)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (a["source"], a["title"], a["summary"], a["url"],
             a["published_at"], a["collected_at"], a["category"],
             a["coins_mentioned"], a["sentiment_keyword"]),
        )
        saved += 1

    conn.commit()
    conn.close()
    return saved


def save_fear_greed(data: dict) -> bool:
    """Fear & Greed Index를 DB에 저장."""
    conn = get_db()
    # 같은 시간대 중복 방지 (1시간 이내)
    existing = conn.execute(
        "SELECT 1 FROM fear_greed_index WHERE timestamp >= datetime(?, '-1 hour')",
        (data["timestamp"],),
    ).fetchone()
    if existing:
        conn.close()
        return False

    conn.execute(
        "INSERT INTO fear_greed_index (timestamp, value, classification, collected_at) VALUES (?, ?, ?, ?)",
        (data["timestamp"], data["value"], data["classification"], data["collected_at"]),
    )
    conn.commit()
    conn.close()
    return True


def collect_all() -> None:
    """전체 수집 실행."""
    logger.info("=== 뉴스 수집 시작 ===")

    # 1. RSS 뉴스
    rss_articles = fetch_all_rss()
    rss_saved = save_articles(rss_articles) if rss_articles else 0
    logger.info("RSS 뉴스: %d건 수집, %d건 신규 저장", len(rss_articles), rss_saved)

    # 2. 업비트 공지
    upbit_articles = fetch_upbit_notices()
    upbit_saved = save_articles(upbit_articles) if upbit_articles else 0
    logger.info("업비트 공지: %d건 수집, %d건 신규 저장", len(upbit_articles), upbit_saved)

    # 3. Fear & Greed Index
    fg = fetch_fear_greed()
    if fg:
        fg_saved = save_fear_greed(fg)
        logger.info("Fear & Greed: %d (%s) %s",
                     fg["value"], fg["classification"],
                     "저장" if fg_saved else "중복 스킵")

    logger.info("=== 수집 완료 (RSS %d + 업비트 %d + F&G) ===", rss_saved, upbit_saved)


def main() -> None:
    """진입점."""
    from cryptobot.logging_config import setup_logging
    setup_logging("news", "INFO")

    logger.info("=== 뉴스 수집기 시작 ===")

    # 시작 시 즉시 1회 수집
    collect_all()

    # 30분 주기 스케줄러
    scheduler = BlockingScheduler()
    scheduler.add_job(collect_all, "interval", minutes=30, id="news_collect")

    def shutdown(*args):
        logger.info("=== 뉴스 수집기 종료 ===")
        if scheduler.running:
            scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("스케줄러 시작 (30분 간격)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        shutdown()


if __name__ == "__main__":
    main()
