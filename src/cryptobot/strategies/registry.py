"""전략 레지스트리.

NestJS의 DI 컨테이너처럼, 전략을 이름으로 등록하고 조회한다.
시장 상태에 따라 적합한 전략을 자동으로 선택할 수 있다.
"""

import logging

from cryptobot.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """전략 등록/조회/선택.

    사용법:
        registry = StrategyRegistry()
        registry.register(VolatilityBreakout())
        registry.register(RSIMeanReversion())

        # 이름으로 조회
        strategy = registry.get("volatility_breakout")

        # 시장 상태로 자동 선택
        strategy = registry.select_by_market("bullish")
    """

    def __init__(self) -> None:
        self._strategies: dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy) -> None:
        """전략 등록."""
        name = strategy.info().name
        self._strategies[name] = strategy
        logger.info("전략 등록: %s (%s)", name, strategy.info().display_name)

    def get(self, name: str) -> BaseStrategy | None:
        """이름으로 전략 조회."""
        return self._strategies.get(name)

    def list_all(self) -> list[BaseStrategy]:
        """등록된 모든 전략 반환."""
        return list(self._strategies.values())

    def list_names(self) -> list[str]:
        """등록된 전략 이름 목록."""
        return list(self._strategies.keys())

    def select_by_market(self, market_state: str) -> BaseStrategy | None:
        """시장 상태에 적합한 전략을 자동 선택.

        Args:
            market_state: "bullish" / "sideways" / "bearish"

        Returns:
            가장 적합한 전략 (없으면 None)
        """
        candidates = [s for s in self._strategies.values() if market_state in s.info().market_states]

        if not candidates:
            logger.warning("시장 상태 '%s'에 적합한 전략 없음", market_state)
            return None

        # 여러 후보 중 첫 번째 반환 (나중에 LLM이 선택하도록 확장 가능)
        selected = candidates[0]
        logger.info(
            "시장 상태 '%s' → 전략 선택: %s",
            market_state,
            selected.info().display_name,
        )
        return selected

    def select_all_for_market(self, market_state: str) -> list[BaseStrategy]:
        """시장 상태에 적합한 모든 전략 반환."""
        return [s for s in self._strategies.values() if market_state in s.info().market_states]
