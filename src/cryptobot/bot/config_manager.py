"""봇 설정 캐시 관리."""

import logging

logger = logging.getLogger(__name__)


class ConfigManager:
    """bot_config 캐시 + 조회."""

    def __init__(self, db) -> None:
        self._db = db
        self._config_cache: dict[str, str] = {}
        self._strategy_params_cache: dict[str, str | None] = {}
        self.refresh()

    def refresh(self) -> None:
        """bot_config + strategy params 캐시 갱신."""
        rows = self._db.execute("SELECT key, value FROM bot_config").fetchall()
        self._config_cache = {r["key"]: r["value"] for r in rows}

        rows = self._db.execute("SELECT name, default_params_json FROM strategies").fetchall()
        self._strategy_params_cache = {r["name"]: r["default_params_json"] for r in rows}

    def get(self, key: str, default: str = "") -> str:
        """캐시에서 설정 값 조회."""
        return self._config_cache.get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        """설정 bool 값 조회."""
        return self.get(key, str(default)).lower() == "true"

    def get_strategy_params_json(self, strategy_name: str) -> str | None:
        """전략 파라미터 JSON 조회."""
        return self._strategy_params_cache.get(strategy_name)
