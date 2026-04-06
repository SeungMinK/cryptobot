.PHONY: start bot api web news tunnel install test lint

# 전체 실행 (봇 + API + Admin + 터널)
start:
	bash scripts/start_all.sh

# 개별 실행
bot:
	.venv/bin/python -m cryptobot.bot.main

api:
	.venv/bin/uvicorn cryptobot.api.main:app --host 0.0.0.0 --port 8000 --app-dir src

web:
	cd admin && npm run dev

news:
	.venv/bin/python news-collector/collector.py

tunnel:
	cloudflared tunnel run cryptobot-api

# 개발
install:
	pip install -e ".[dev]"
	cd admin && npm install

test:
	.venv/bin/python -m pytest tests/ -v

lint:
	.venv/bin/ruff check src/ tests/
	.venv/bin/ruff format --check src/ tests/
