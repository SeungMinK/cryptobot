"""config 모듈 테스트."""

from cryptobot.bot.config import Config, UpbitConfig


def test_default_config():
    """기본 설정값이 올바르게 로딩되는지 확인."""
    cfg = Config()
    assert cfg.bot.coin == "KRW-BTC"
    assert cfg.bot.log_level == "INFO"


def test_upbit_config_not_configured():
    """API Key가 없으면 is_configured가 False."""
    upbit = UpbitConfig(access_key="", secret_key="")
    assert upbit.is_configured is False


def test_upbit_config_configured():
    """API Key가 있으면 is_configured가 True."""
    upbit = UpbitConfig(access_key="test_key", secret_key="test_secret")
    assert upbit.is_configured is True
