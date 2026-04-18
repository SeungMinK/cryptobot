"""#154 — 뉴스 impact_score/scope 태깅 테스트.

- tagger.py 분류 정확성
- 프롬프트에 impact/scope 포맷 반영
- 뉴스 정렬이 impact 내림차순인지
"""

import sys
import tempfile
from pathlib import Path

import pytest

# news-collector/sources 를 import path에 추가
_NEWS_COLLECTOR_DIR = Path(__file__).resolve().parent.parent / "news-collector"
sys.path.insert(0, str(_NEWS_COLLECTOR_DIR))

from sources.tagger import classify_scope, score_impact, tag_article  # noqa: E402

from cryptobot.data.database import Database  # noqa: E402
from cryptobot.llm.analyzer import LLMAnalyzer  # noqa: E402


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    yield db
    db.close()


# ===================================================================
# tagger.classify_scope
# ===================================================================


def test_classify_scope_macro_regulation():
    assert classify_scope("SEC approves Bitcoin ETF") == "macro"
    assert classify_scope("Fed cuts interest rate by 0.25%") == "macro"
    assert classify_scope("Treasury warns of recession risk") == "macro"


def test_classify_scope_micro_project():
    assert classify_scope("HIVE raises $75M for mining expansion") == "micro"
    assert classify_scope("Uniswap launches v4") == "micro"
    assert classify_scope("CEO of Coinbase resigns") == "micro"


def test_classify_scope_combined():
    # macro 키워드가 하나라도 있으면 macro
    assert classify_scope("SEC sues Binance CEO") == "macro"


# ===================================================================
# tagger.score_impact
# ===================================================================


def test_score_impact_high_macro():
    # 규제 + 고영향 키워드 → 9
    assert score_impact("SEC bans all Bitcoin ETFs") == 9


def test_score_impact_high_micro():
    # 개별 + 고영향 → 7
    assert score_impact("Exchange hacked, $200M stolen") == 7


def test_score_impact_medium_macro():
    # 거시 + 중간 → 6
    assert score_impact("Fed warns of inflation risks") == 6


def test_score_impact_medium_micro():
    # 개별 + 중간 → 4
    assert score_impact("Project launches new feature") == 4


def test_score_impact_low_default():
    # 중립적인 뉴스 → macro 5 / micro 3
    assert score_impact("Bitcoin price analysis for Q2") >= 3


# ===================================================================
# tag_article integration
# ===================================================================


def test_tag_article_returns_both_fields():
    result = tag_article("Fed cuts interest rate by 0.25%")
    assert result["scope"] == "macro"
    assert isinstance(result["impact_score"], int)
    assert 0 <= result["impact_score"] <= 10


# ===================================================================
# _get_news_text — prompt format
# ===================================================================


def test_news_text_includes_impact_and_scope(db):
    """프롬프트에 |macro|impact=N| 형식이 포함된다."""
    db.execute(
        """INSERT INTO news_articles
        (source, title, collected_at, impact_score, scope, sentiment_keyword)
        VALUES ('test', 'SEC sues major exchange', datetime('now'), 9, 'macro', 'negative')"""
    )
    db.commit()

    analyzer = LLMAnalyzer(db)
    text = analyzer._get_news_text()
    assert "macro" in text
    assert "impact=9" in text
    assert "SEC sues major exchange" in text


def test_news_text_sorts_by_impact_desc(db):
    """impact 내림차순으로 정렬된다."""
    # low impact 먼저 insert
    db.execute(
        """INSERT INTO news_articles
        (source, title, collected_at, impact_score, scope)
        VALUES ('test', 'Low news', datetime('now'), 2, 'micro')"""
    )
    db.execute(
        """INSERT INTO news_articles
        (source, title, collected_at, impact_score, scope)
        VALUES ('test', 'High news', datetime('now'), 9, 'macro')"""
    )
    db.commit()

    analyzer = LLMAnalyzer(db)
    text = analyzer._get_news_text()
    # High news 가 Low news 보다 먼저 나와야 함
    assert text.index("High news") < text.index("Low news")


def test_news_text_null_impact_fallback(db):
    """impact_score/scope가 NULL이어도 에러 없이 렌더."""
    db.execute(
        """INSERT INTO news_articles
        (source, title, collected_at, sentiment_keyword)
        VALUES ('test', 'Legacy news without tags', datetime('now'), 'neutral')"""
    )
    db.commit()
    analyzer = LLMAnalyzer(db)
    text = analyzer._get_news_text()
    assert "Legacy news without tags" in text
    # impact=N 섹션이 없어야 함 (NULL이므로)
    assert "impact=" not in text.split("Legacy news")[0].split("\n")[-1]
