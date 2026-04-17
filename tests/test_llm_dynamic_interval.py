"""LLM 동적 호출 간격 판정 테스트.

_get_dynamic_interval_minutes()는 매매/포지션만으로 ACTIVE/NORMAL/QUIET를
판정해야 한다. 뉴스 건수는 제외 (수집기 기본 출력이 과반 시간대 ACTIVE를
오판정하는 원인이었음 — issue #160).
"""

import tempfile
from pathlib import Path

from cryptobot.data.database import Database
from cryptobot.llm.analyzer import LLMAnalyzer


def _make_analyzer():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    return LLMAnalyzer(db), db


def _insert_recent_news(db, count: int) -> None:
    for i in range(count):
        db.execute(
            "INSERT INTO news_articles (title, source, url, collected_at) "
            "VALUES (?, ?, ?, datetime('now', '-10 minutes'))",
            (f"뉴스{i}", "test", f"http://example.com/{i}"),
        )
    db.commit()


def _insert_recent_buy(db, coin: str, closed: bool = False) -> int:
    cur = db.execute(
        "INSERT INTO trades (coin, side, price, amount, total_krw, fee_krw, strategy, timestamp) "
        "VALUES (?, 'buy', 100, 1, 100, 0.05, 'test', datetime('now', '-10 minutes'))",
        (coin,),
    )
    buy_id = cur.lastrowid
    if closed:
        db.execute(
            "INSERT INTO trades (coin, side, price, amount, total_krw, fee_krw, strategy, timestamp, buy_trade_id) "
            "VALUES (?, 'sell', 110, 1, 110, 0.05, 'test', datetime('now', '-5 minutes'), ?)",
            (coin, buy_id),
        )
    db.commit()
    return buy_id


def test_quiet_when_no_trades_no_positions():
    """매매 0 + 포지션 0 → QUIET."""
    analyzer, db = _make_analyzer()
    assert analyzer._get_dynamic_interval_minutes() == analyzer.INTERVAL_QUIET_MIN


def test_quiet_ignores_news_flood():
    """뉴스가 시간당 10건이어도 매매/포지션 0이면 QUIET (뉴스는 판정 제외)."""
    analyzer, db = _make_analyzer()
    _insert_recent_news(db, 10)
    assert analyzer._get_dynamic_interval_minutes() == analyzer.INTERVAL_QUIET_MIN


def test_active_when_many_trades():
    """최근 1시간 매매 2건+ → ACTIVE."""
    analyzer, db = _make_analyzer()
    _insert_recent_buy(db, "KRW-BTC", closed=True)
    _insert_recent_buy(db, "KRW-ETH", closed=True)
    assert analyzer._get_dynamic_interval_minutes() == analyzer.INTERVAL_ACTIVE_MIN


def test_active_when_many_positions():
    """열린 포지션 3개+ → ACTIVE."""
    analyzer, db = _make_analyzer()
    _insert_recent_buy(db, "KRW-BTC")
    _insert_recent_buy(db, "KRW-ETH")
    _insert_recent_buy(db, "KRW-XRP")
    assert analyzer._get_dynamic_interval_minutes() == analyzer.INTERVAL_ACTIVE_MIN


def test_normal_when_one_open_position():
    """포지션 1개 + 매매 0 → NORMAL (활발 아님, 한산도 아님)."""
    analyzer, db = _make_analyzer()
    _insert_recent_buy(db, "KRW-BTC")
    # buy만 존재 — trades 테이블에 1건 있으므로 trade_count=1, position_count=1
    # trade_count(1) < 2 이고 position_count(1) < 3 이므로 NORMAL
    assert analyzer._get_dynamic_interval_minutes() == analyzer.INTERVAL_NORMAL_MIN
