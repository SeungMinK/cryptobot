"""SQLite 데이터베이스 관리 모듈.

NestJS의 TypeOrmModule + Repository 패턴과 비슷한 역할.
다만 ORM 없이 직접 SQL을 작성한다.
"""

import logging
import sqlite3
from pathlib import Path

from cryptobot.exceptions import DatabaseError

logger = logging.getLogger(__name__)

# 테이블 생성 SQL
_SCHEMA = """
CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    btc_price REAL NOT NULL,
    btc_open_24h REAL,
    btc_high_24h REAL,
    btc_low_24h REAL,
    btc_change_pct_24h REAL,
    btc_volume_24h REAL,
    btc_trade_count_24h INTEGER,
    btc_rsi_14 REAL,
    btc_ma_5 REAL,
    btc_ma_20 REAL,
    btc_ma_60 REAL,
    btc_bb_upper REAL,
    btc_bb_lower REAL,
    btc_atr_14 REAL,
    total_market_volume_krw REAL,
    top10_avg_change_pct REAL,
    market_state TEXT,
    volatility_level TEXT,
    UNIQUE(timestamp)
);

CREATE TABLE IF NOT EXISTS trade_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    coin TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    strategy TEXT NOT NULL,
    confidence REAL,
    trigger_reason TEXT,
    trigger_value REAL,
    current_price REAL,
    target_price REAL,
    executed BOOLEAN DEFAULT FALSE,
    trade_id INTEGER,
    skip_reason TEXT,
    snapshot_id INTEGER,
    FOREIGN KEY (trade_id) REFERENCES trades(id),
    FOREIGN KEY (snapshot_id) REFERENCES market_snapshots(id)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    coin TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    amount REAL NOT NULL,
    total_krw REAL NOT NULL,
    fee_krw REAL NOT NULL,
    strategy TEXT NOT NULL,
    trigger_reason TEXT,
    trigger_value REAL,
    param_k_value REAL,
    param_stop_loss REAL,
    param_trailing_stop REAL,
    market_state_at_trade TEXT,
    btc_price_at_trade REAL,
    rsi_at_trade REAL,
    buy_trade_id INTEGER,
    profit_pct REAL,
    profit_krw REAL,
    hold_duration_minutes INTEGER,
    FOREIGN KEY (buy_trade_id) REFERENCES trades(id)
);

CREATE TABLE IF NOT EXISTS strategy_params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    k_value REAL NOT NULL,
    stop_loss_pct REAL NOT NULL,
    trailing_stop_pct REAL NOT NULL,
    max_positions INTEGER NOT NULL,
    position_size_pct REAL,
    allow_trading BOOLEAN NOT NULL DEFAULT TRUE,
    market_state TEXT,
    aggression REAL,
    llm_reasoning TEXT,
    llm_news_summary TEXT,
    llm_model TEXT,
    period_trade_count INTEGER,
    period_win_rate REAL,
    period_total_pnl_pct REAL
);

CREATE TABLE IF NOT EXISTS daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL UNIQUE,
    starting_balance_krw REAL,
    ending_balance_krw REAL,
    total_asset_value_krw REAL,
    realized_pnl_krw REAL,
    unrealized_pnl_krw REAL,
    daily_return_pct REAL,
    cumulative_return_pct REAL,
    total_trades INTEGER,
    buy_trades INTEGER,
    sell_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate REAL,
    avg_profit_pct REAL,
    avg_loss_pct REAL,
    max_drawdown_pct REAL,
    total_fees_krw REAL,
    active_param_id INTEGER,
    market_state TEXT,
    FOREIGN KEY (active_param_id) REFERENCES strategy_params(id)
);

CREATE TABLE IF NOT EXISTS llm_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model TEXT NOT NULL,
    input_news_count INTEGER,
    input_news_summary TEXT,
    input_market_snapshot_id INTEGER,
    input_recent_trades_count INTEGER,
    input_recent_win_rate REAL,
    output_raw_json TEXT,
    output_market_state TEXT,
    output_aggression REAL,
    output_allow_trading BOOLEAN,
    output_k_value REAL,
    output_stop_loss REAL,
    output_trailing_stop REAL,
    output_reasoning TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    evaluation_period_pnl_pct REAL,
    evaluation_was_good BOOLEAN,
    FOREIGN KEY (input_market_snapshot_id) REFERENCES market_snapshots(id)
);
"""

# 기본 전략 파라미터 (최초 1회 삽입)
_DEFAULT_PARAMS = """
INSERT INTO strategy_params (
    source, k_value, stop_loss_pct, trailing_stop_pct,
    max_positions, position_size_pct, allow_trading, market_state, aggression
) VALUES (
    'default', 0.5, -5.0, -3.0,
    1, 100.0, TRUE, 'sideways', 0.5
);
"""


class Database:
    """SQLite 데이터베이스 연결 관리.

    NestJS에서 TypeOrmModule.forRoot()로 DB 연결하는 것과 동일한 역할.
    with 구문으로 사용하면 자동으로 커넥션을 닫는다.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        """현재 DB 커넥션을 반환한다. 없으면 생성."""
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row  # dict처럼 접근 가능
            self._conn.execute("PRAGMA journal_mode=WAL")  # 동시 읽기 성능 향상
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def initialize(self) -> None:
        """테이블 생성 및 기본 데이터 삽입."""
        try:
            conn = self.connection
            conn.executescript(_SCHEMA)

            # 기본 파라미터가 없으면 삽입
            row = conn.execute("SELECT COUNT(*) FROM strategy_params").fetchone()
            if row[0] == 0:
                conn.executescript(_DEFAULT_PARAMS)
                logger.info("기본 전략 파라미터 삽입 완료")

            conn.commit()
            logger.info("데이터베이스 초기화 완료: %s", self._db_path)
        except sqlite3.Error as e:
            raise DatabaseError(f"데이터베이스 초기화 실패: {e}") from e

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """SQL 실행 후 커서 반환."""
        return self.connection.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """여러 행 삽입."""
        return self.connection.executemany(sql, params_list)

    def commit(self) -> None:
        """트랜잭션 커밋."""
        self.connection.commit()

    def close(self) -> None:
        """커넥션 종료."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("데이터베이스 커넥션 종료")

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
