---
name: lint
description: Python ruff + TypeScript tsc 린트/포맷 체크를 한번에 실행.
disable-model-invocation: true
argument-hint: "[--fix]"
allowed-tools: Bash(.venv/bin/ruff *) Bash(npx tsc *)
---

Python과 TypeScript 린트를 한번에 실행한다.

## Python (ruff)

```bash
cd /Users/seungminkim/worksapce/cryptobot
echo "=== Python: ruff check ==="
.venv/bin/ruff check src/ tests/
echo "=== Python: ruff format check ==="
.venv/bin/ruff format --check src/ tests/
```

`--fix` 인자가 전달되면 자동 수정:
```bash
.venv/bin/ruff check --fix src/ tests/
.venv/bin/ruff format src/ tests/
```

## TypeScript (tsc)

```bash
cd /Users/seungminkim/worksapce/cryptobot/admin
echo "=== TypeScript: tsc --noEmit ==="
npx tsc --noEmit
```

- 에러가 있으면 파일:라인 단위로 정리해서 보여주기
- `--fix` 인자 시 Python은 자동 수정, TypeScript는 수정 방안 제시
