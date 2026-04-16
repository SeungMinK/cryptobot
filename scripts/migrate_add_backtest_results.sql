-- 백테스트 결과 저장 테이블
CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date DATE NOT NULL,
    strategy_name TEXT NOT NULL,
    coin TEXT NOT NULL,
    period TEXT NOT NULL,
    num_trades INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    total_return_pct REAL NOT NULL,
    max_drawdown_pct REAL NOT NULL,
    sharpe_ratio REAL NOT NULL,
    avg_profit_pct REAL NOT NULL,
    avg_loss_pct REAL NOT NULL,
    best_trade_pct REAL NOT NULL,
    worst_trade_pct REAL NOT NULL,
    params_json TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bt_run_date ON backtest_results(run_date, strategy_name, coin);
