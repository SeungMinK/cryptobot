"""뉴스 impact_score / scope 규칙 기반 태깅 (#154).

LLM 호출 없이 키워드 매칭으로 분류. 비용 0, 정확도 제한.
후일 Haiku 기반 고정밀 태깅으로 업그레이드 여지를 남겨둔다.

기준:
- scope:
  - "macro": Fed/규제/거시경제/ETF/SEC/Treasury 등 시장 전체 영향
  - "micro": 개별 프로젝트/기업 소식 (펀딩, 제품, 파트너십)
- impact_score (0~10):
  - 10: 규제 결정, Fed 금리, 시장 전체 폭락/폭등
  - 7-9: ETF 승인/거절, 메이저 거래소 이슈, 주요 코인 기술 이슈
  - 4-6: 일반 시장 움직임, 분석/전망
  - 1-3: 개별 프로젝트 소식, 소형 업데이트
  - 0: 판단 불가 (폴백)
"""

from __future__ import annotations

# 거시 키워드 (macro) — 시장 전체 영향 가능성
_MACRO_KEYWORDS = (
    # 규제/정부
    "sec ",
    "regulation",
    "regulator",
    "regulatory",
    "treasury",
    "congress",
    "senate",
    "doj",
    "cftc",
    "irs",
    "fatf",
    # 중앙은행/통화
    "fed ",
    "federal reserve",
    "interest rate",
    "inflation",
    "recession",
    "cpi",
    "fomc",
    "rate cut",
    "rate hike",
    # ETF
    "etf",
    "etn",
    "spot bitcoin",
    "spot ether",
    # 거시 키워드
    "market crash",
    "market rally",
    "macro",
    "geopolitic",
)

# 초고영향 키워드 (impact 8~10)
_HIGH_IMPACT_KEYWORDS = (
    "crash",
    "plunge",
    "surge",
    "soar",
    "bans",
    "banned",
    "ban ",
    "lawsuit",
    "indictment",
    "hack",
    "hacked",
    "exploit",
    "collapse",
    "bankruptcy",
    "halting",
    "halted",
    "approved",
    "rejected",
    "breakthrough",
    "emergency",
)

# 중간 영향 키워드 (impact 5~7)
_MEDIUM_IMPACT_KEYWORDS = (
    "warning",
    "warns",
    "drop",
    "falls",
    "rises",
    "growth",
    "partnership",
    "launch",
    "launches",
    "upgrade",
    "update",
    "investment",
    "funding",
    "raise",
    "raised",
)


def _lower(text: str) -> str:
    return (text or "").lower()


def classify_scope(title: str, summary: str = "") -> str:
    """제목+요약에 macro 키워드가 하나라도 있으면 "macro", 아니면 "micro"."""
    text = f"{_lower(title)} {_lower(summary)}"
    for kw in _MACRO_KEYWORDS:
        if kw in text:
            return "macro"
    return "micro"


def score_impact(title: str, summary: str = "", scope: str | None = None) -> int:
    """영향도 점수 계산 (0~10).

    - 고영향 키워드 존재 + macro scope: 9
    - 고영향 키워드 + micro: 7
    - 중간 키워드 + macro: 6
    - 중간 키워드 + micro: 4
    - 외: scope가 macro면 5, micro면 3, 불명이면 0
    """
    text = f"{_lower(title)} {_lower(summary)}"
    scope = scope or classify_scope(title, summary)

    has_high = any(kw in text for kw in _HIGH_IMPACT_KEYWORDS)
    has_medium = any(kw in text for kw in _MEDIUM_IMPACT_KEYWORDS)

    if has_high:
        return 9 if scope == "macro" else 7
    if has_medium:
        return 6 if scope == "macro" else 4
    return 5 if scope == "macro" else 3


def tag_article(title: str, summary: str = "") -> dict:
    """기사에 scope/impact_score 태깅. dict로 반환.

    >>> tag_article("Fed cuts interest rate")
    {'scope': 'macro', 'impact_score': 6}
    >>> tag_article("HIVE raises $75M for mining")
    {'scope': 'micro', 'impact_score': 4}
    """
    scope = classify_scope(title, summary)
    impact = score_impact(title, summary, scope)
    return {"scope": scope, "impact_score": impact}
