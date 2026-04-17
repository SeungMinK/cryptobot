---
name: test
description: pytest 실행. 인자 없으면 전체 테스트, 있으면 해당 경로/옵션으로 실행.
disable-model-invocation: true
argument-hint: "[pytest args, e.g. tests/test_api.py -k login]"
allowed-tools: Bash(.venv/bin/python *)
---

프로젝트 루트에서 pytest를 실행한다.

```bash
cd /Users/seungminkim/worksapce/cryptobot
.venv/bin/python -m pytest $ARGUMENTS -v --tb=short
```

- 인자가 없으면 `tests/` 전체 실행
- 인자가 있으면 그대로 pytest에 전달 (예: `tests/test_api.py -k login`)
- 실패한 테스트가 있으면 원인을 분석하고 수정 방안을 제시
