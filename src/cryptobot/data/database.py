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
    strategy_params_json TEXT,
    strategy_selection_reason TEXT,
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

CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    market_states TEXT NOT NULL,
    timeframe TEXT,
    difficulty TEXT,
    default_params_json TEXT,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    is_available BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategy_activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    strategy_name TEXT NOT NULL,
    action TEXT NOT NULL,
    source TEXT NOT NULL,
    market_state TEXT,
    reason TEXT,
    previous_strategy TEXT,
    performance_at_switch_json TEXT,
    FOREIGN KEY (strategy_name) REFERENCES strategies(name)
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at DATETIME
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

CREATE TABLE IF NOT EXISTS bot_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL DEFAULT 'string',
    category TEXT NOT NULL DEFAULT 'general',
    display_name TEXT NOT NULL,
    description TEXT,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
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

# 전략 마스터 데이터
_DEFAULT_STRATEGIES = [
    {
        "name": "volatility_breakout",
        "display_name": "변동성 돌파",
        "description": "시가 + 전일 변동폭 × K 돌파 시 매수. 래리 윌리엄스의 단기 전략.",
        "category": "volatility",
        "market_states": "bullish",
        "timeframe": "1d",
        "difficulty": "easy",
        "default_params_json": '{"k_value": 0.5}',
        "is_active": True,
    },
    {
        "name": "ma_crossover",
        "display_name": "이동평균 교차",
        "description": "단기 MA가 장기 MA를 돌파하면 매수/매도. 가장 고전적인 추세 추종 전략.",
        "category": "trend",
        "market_states": "bullish,bearish",
        "timeframe": "1d",
        "difficulty": "easy",
        "default_params_json": '{"short_period": 5, "long_period": 20}',
        "is_active": False,
    },
    {
        "name": "macd",
        "display_name": "MACD",
        "description": "MACD-시그널 라인 교차로 추세 강도와 방향 판단.",
        "category": "trend",
        "market_states": "bullish,bearish",
        "timeframe": "1d",
        "difficulty": "easy",
        "default_params_json": '{"fast": 12, "slow": 26, "signal_period": 9}',
        "is_active": False,
    },
    {
        "name": "supertrend",
        "display_name": "슈퍼트렌드",
        "description": "ATR 기반 동적 지지/저항선으로 추세 추종. 변동성 적응형.",
        "category": "trend",
        "market_states": "bullish,bearish",
        "timeframe": "1d",
        "difficulty": "medium",
        "default_params_json": '{"st_period": 10, "st_multiplier": 3.0}',
        "is_active": False,
    },
    {
        "name": "rsi_mean_reversion",
        "display_name": "RSI 평균 회귀",
        "description": "RSI 과매도 반등 매수, 과매수 하락 매도. 횡보장 전용.",
        "category": "mean_reversion",
        "market_states": "sideways",
        "timeframe": "1h",
        "difficulty": "easy",
        "default_params_json": '{"rsi_period": 14, "oversold": 30, "overbought": 70}',
        "is_active": False,
    },
    {
        "name": "bollinger_bands",
        "display_name": "볼린저 밴드",
        "description": "밴드 이탈 후 복귀 시 반전 진입. 횡보장에서 높은 승률.",
        "category": "mean_reversion",
        "market_states": "sideways",
        "timeframe": "1h",
        "difficulty": "easy",
        "default_params_json": '{"bb_period": 20, "bb_std": 2.0}',
        "is_active": False,
    },
    {
        "name": "grid_trading",
        "display_name": "그리드 트레이딩",
        "description": "가격 범위를 격자로 나누어 분할 매수/매도. 추세 예측 불필요.",
        "category": "grid",
        "market_states": "sideways",
        "timeframe": "1h",
        "difficulty": "medium",
        "default_params_json": '{"grid_count": 10, "range_pct": 10.0}',
        "is_active": False,
    },
    {
        "name": "breakout_momentum",
        "display_name": "브레이크아웃 모멘텀",
        "description": "N일 최고가 돌파 매수. 터틀 트레이딩 핵심 전략.",
        "category": "momentum",
        "market_states": "bullish,sideways",
        "timeframe": "1d",
        "difficulty": "easy",
        "default_params_json": '{"entry_period": 20, "exit_period": 10}',
        "is_active": False,
    },
    {
        "name": "bollinger_squeeze",
        "display_name": "볼린저 스퀴즈",
        "description": "밴드 수축 후 폭발적 움직임 포착. 횡보→추세 전환 구간.",
        "category": "volatility",
        "market_states": "sideways,bullish",
        "timeframe": "1d",
        "difficulty": "medium",
        "default_params_json": '{"bb_period": 20, "bb_std": 2.0, "squeeze_lookback": 120}',
        "is_active": False,
    },
]

# 봇 설정 기본값
_DEFAULT_BOT_CONFIG = [
    {
        "key": "slack_tick_report",
        "value": "false",
        "value_type": "bool",
        "category": "notification",
        "display_name": "틱별 판단 리포트",
        "description": "매 스케줄러 실행 시 매수/매도/HOLD 판단 근거를 Slack으로 발송",
    },
    {
        "key": "slack_trade_notification",
        "value": "true",
        "value_type": "bool",
        "category": "notification",
        "display_name": "매매 체결 알림",
        "description": "매수/매도 체결 시 Slack 알림 발송",
    },
    {
        "key": "slack_daily_report",
        "value": "true",
        "value_type": "bool",
        "category": "notification",
        "display_name": "일일 정산 리포트",
        "description": "자정에 일일 매매 성과를 Slack으로 발송",
    },
    {
        "key": "tick_interval_seconds",
        "value": "10",
        "value_type": "int",
        "category": "bot",
        "display_name": "판단 주기 (초)",
        "description": "매매 신호 판단 간격. 너무 짧으면 API 호출 제한에 걸릴 수 있음",
    },
    {
        "key": "position_size_pct",
        "value": "100",
        "value_type": "float",
        "category": "risk",
        "display_name": "포지션 크기 (%)",
        "description": "가용 잔고 대비 최대 매수 비율. 50이면 잔고의 50%까지만 매수",
    },
    {
        "key": "stop_loss_pct",
        "value": "-5.0",
        "value_type": "float",
        "category": "risk",
        "display_name": "손절률 (%)",
        "description": "매수가 대비 이 비율만큼 하락하면 자동 매도",
    },
    {
        "key": "trailing_stop_pct",
        "value": "-3.0",
        "value_type": "float",
        "category": "risk",
        "display_name": "트레일링 스탑 (%)",
        "description": "최고가 대비 이 비율만큼 하락하면 자동 매도",
    },
    {
        "key": "max_daily_trades",
        "value": "10",
        "value_type": "int",
        "category": "risk",
        "display_name": "일일 최대 거래 횟수",
        "description": "하루에 이 횟수 이상 거래하면 매매 중단",
    },
    {
        "key": "max_daily_loss_pct",
        "value": "-10.0",
        "value_type": "float",
        "category": "risk",
        "display_name": "일일 최대 손실률 (%)",
        "description": "일일 누적 손실이 이 비율을 초과하면 매매 중단",
    },
    {
        "key": "max_consecutive_losses",
        "value": "3",
        "value_type": "int",
        "category": "risk",
        "display_name": "연속 손실 허용 횟수",
        "description": "연속으로 이 횟수만큼 손실 시 매매 중단",
    },
    {
        "key": "k_value",
        "value": "0.5",
        "value_type": "float",
        "category": "strategy",
        "display_name": "K 값 (변동성 돌파)",
        "description": "변동성 돌파 전략의 K 계수. 높을수록 보수적 (0.0~1.0)",
    },
    {
        "key": "allow_trading",
        "value": "true",
        "value_type": "bool",
        "category": "bot",
        "display_name": "매매 허용",
        "description": "false로 설정하면 봇이 신호만 기록하고 실제 매매는 하지 않음",
    },
]


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
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
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

            # 전략 마스터 데이터 삽입
            row = conn.execute("SELECT COUNT(*) FROM strategies").fetchone()
            if row[0] == 0:
                for s in _DEFAULT_STRATEGIES:
                    conn.execute(
                        """
                        INSERT INTO strategies (
                            name, display_name, description, category,
                            market_states, timeframe, difficulty,
                            default_params_json, is_active
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            s["name"],
                            s["display_name"],
                            s["description"],
                            s["category"],
                            s["market_states"],
                            s["timeframe"],
                            s["difficulty"],
                            s["default_params_json"],
                            s["is_active"],
                        ),
                    )
                logger.info("전략 마스터 데이터 삽입 완료 (%d개)", len(_DEFAULT_STRATEGIES))

            # 봇 설정 기본값 삽입
            row = conn.execute("SELECT COUNT(*) FROM bot_config").fetchone()
            if row[0] == 0:
                for cfg in _DEFAULT_BOT_CONFIG:
                    conn.execute(
                        """
                        INSERT INTO bot_config (key, value, value_type, category, display_name, description)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (cfg["key"], cfg["value"], cfg["value_type"], cfg["category"], cfg["display_name"], cfg["description"]),
                    )
                logger.info("봇 설정 기본값 삽입 완료 (%d개)", len(_DEFAULT_BOT_CONFIG))

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
