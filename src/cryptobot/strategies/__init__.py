"""매매 전략 모듈.

모든 전략은 BaseStrategy를 상속하고, 동일한 인터페이스로 동작한다.
NestJS에서 interface를 정의하고 여러 구현체를 만드는 것과 동일.
"""

from cryptobot.strategies.base import BaseStrategy, Signal, StrategyInfo
from cryptobot.strategies.registry import StrategyRegistry

__all__ = ["BaseStrategy", "Signal", "StrategyInfo", "StrategyRegistry"]
