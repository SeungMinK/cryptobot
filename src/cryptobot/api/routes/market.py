"""시장 현황 라우트."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from cryptobot.api.auth import UserResponse, get_current_user
from cryptobot.api.deps import get_db

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/current")
def get_current_market(_: UserResponse = Depends(get_current_user)):
    """현재 시장 상태 (BTC 기준 최근 스냅샷)."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM market_snapshots WHERE coin = 'KRW-BTC' ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if row is None:
        # BTC 없으면 아무거나
        row = db.execute("SELECT * FROM market_snapshots ORDER BY id DESC LIMIT 1").fetchone()

    if row is None:
        return {"status": "no_data", "message": "시장 데이터 없음"}

    return dict(row)


@router.get("/coins")
def get_monitored_coins(_: UserResponse = Depends(get_current_user)):
    """현재 모니터링 중인 코인별 최신 데이터."""
    db = get_db()

    # 모니터링 중인 코인 = 최근 1시간 내 스냅샷이 있는 코인들
    rows = db.execute(
        """
        SELECT coin, MAX(id) as latest_id
        FROM (
            SELECT 'KRW-BTC' as coin, id, btc_price as price, market_state, btc_rsi_14 as rsi, btc_change_pct_24h as change_pct
            FROM market_snapshots
            WHERE timestamp >= datetime('now', '-1 hour')
        )
        GROUP BY coin
        """
    ).fetchall()

    # 전체 코인의 최신 스냅샷 (각 코인별)
    # market_snapshots는 현재 BTC만 저장하므로, trade_signals에서 코인 목록을 가져옴
    active_coins = db.execute(
        """
        SELECT DISTINCT coin FROM trade_signals
        WHERE timestamp >= datetime('now', '-1 hour')
        ORDER BY coin
        """
    ).fetchall()

    result = []
    for row in active_coins:
        coin = row["coin"]
        # 최신 신호에서 가격/상태 가져오기
        latest = db.execute(
            """
            SELECT ts.coin, ts.current_price, ts.strategy, ts.signal_type, ts.confidence,
                   ts.trigger_reason, ts.timestamp,
                   ms.market_state, ms.btc_rsi_14 as rsi
            FROM trade_signals ts
            LEFT JOIN market_snapshots ms ON ts.snapshot_id = ms.id
            WHERE ts.coin = ?
            ORDER BY ts.id DESC LIMIT 1
            """,
            (coin,),
        ).fetchone()

        if latest:
            # 보유 여부 확인
            held = db.execute(
                """
                SELECT t.price as buy_price, t.total_krw, t.timestamp as buy_time
                FROM trades t
                WHERE t.coin = ? AND t.side = 'buy'
                AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side = 'sell')
                ORDER BY t.id DESC LIMIT 1
                """,
                (coin,),
            ).fetchone()

            entry = dict(latest)
            if held:
                entry["holding"] = True
                entry["buy_price"] = held["buy_price"]
                entry["buy_total_krw"] = held["total_krw"]
                entry["buy_time"] = held["buy_time"]
                entry["unrealized_pnl_pct"] = round(
                    (entry["current_price"] - held["buy_price"]) / held["buy_price"] * 100, 2
                ) if entry["current_price"] and held["buy_price"] else 0
            else:
                entry["holding"] = False

            result.append(entry)

    return result


@router.get("/snapshots")
def get_snapshots(
    limit: int = Query(60, ge=1, le=1440),
    _: UserResponse = Depends(get_current_user),
):
    """최근 스냅샷 이력."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM market_snapshots ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


@router.get("/signals")
def get_recent_signals(
    limit: int = Query(50, ge=1, le=200),
    _: UserResponse = Depends(get_current_user),
):
    """최근 매매 신호."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM trade_signals ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


class CoinScanRequest(BaseModel):
    max_coins: int = 5
    min_volume_krw: float = 1_000_000_000
    min_price_krw: float = 1_000


@router.post("/scan-preview")
def scan_coins_preview(body: CoinScanRequest, _: UserResponse = Depends(get_current_user)):
    """코인 선별 미리보기. 필터 조건을 바꿔서 어떤 코인이 선별되는지 확인."""
    from cryptobot.bot.scanner import CoinScanner

    scanner = CoinScanner(
        min_volume_krw=body.min_volume_krw,
        min_price_krw=body.min_price_krw,
        max_coins=body.max_coins,
    )
    return scanner.scan_top_coins()


@router.get("/scan-current")
def scan_coins_current(_: UserResponse = Depends(get_current_user)):
    """현재 설정 기준 코인 선별 결과."""
    from cryptobot.bot.scanner import CoinScanner

    db = get_db()

    def _get(key: str, default: str) -> str:
        row = db.execute("SELECT value FROM bot_config WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    scanner = CoinScanner(
        min_volume_krw=float(_get("min_volume_krw", "1000000000")),
        min_price_krw=float(_get("min_price_krw", "1000")),
        max_coins=int(_get("max_coins", "5")),
    )
    return scanner.scan_top_coins()


@router.get("/coin-strategies")
def get_coin_strategies(_: UserResponse = Depends(get_current_user)):
    """각 코인별 현재 적용 전략 + 시장 상태."""
    db = get_db()

    # 최근 신호에서 코인별 전략/시장 확인
    rows = db.execute(
        """
        SELECT ts.coin, ts.strategy, ms.market_state,
               ts.current_price, ts.confidence, ts.signal_type
        FROM trade_signals ts
        LEFT JOIN market_snapshots ms ON ts.snapshot_id = ms.id
        WHERE ts.id IN (
            SELECT MAX(id) FROM trade_signals
            WHERE timestamp >= datetime('now', '-1 hour')
            GROUP BY coin
        )
        ORDER BY ts.coin
        """
    ).fetchall()

    # 보유 여부도 확인
    result = []
    for r in rows:
        coin = r["coin"]
        held = db.execute(
            """
            SELECT 1 FROM trades t WHERE t.coin = ? AND t.side = 'buy'
            AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side = 'sell')
            LIMIT 1
            """,
            (coin,),
        ).fetchone()

        result.append({
            "coin": coin,
            "strategy": r["strategy"],
            "market_state": r["market_state"],
            "current_price": r["current_price"],
            "signal_type": r["signal_type"],
            "confidence": r["confidence"],
            "holding": held is not None,
        })

    return result
