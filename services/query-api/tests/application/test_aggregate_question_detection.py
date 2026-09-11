import pytest

from application.aggregate_question_detection import is_busiest_symbol_question, is_list_all_articles_question


@pytest.mark.parametrize(
    "question",
    [
        "what symbol have most news in a day?",
        "which symbol has the most articles in a day",
        "what ticker has the least news?",
        "who has the fewest articles this week",
        "highest number of news articles for a symbol",
    ],
)
def test_matches_aggregate_phrasings(question: str) -> None:
    assert is_busiest_symbol_question(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "what's new with Apple?",
        "any consecutive news in a week?",
        "give me the link to the Anthropic article",
        "what happened with TSLA today",
    ],
)
def test_does_not_match_ordinary_content_questions(question: str) -> None:
    assert is_busiest_symbol_question(question) is False


@pytest.mark.parametrize(
    "question",
    [
        "give me all 66 articles",
        "list all the news for GOOG",
        "can I see every article about TSLA",
        "give me the complete list of news",
    ],
)
def test_matches_list_all_phrasings(question: str) -> None:
    assert is_list_all_articles_question(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "what's new with Apple?",
        "what symbol have most news in a day?",
        "give me the link to the Anthropic article",
    ],
)
def test_list_all_does_not_match_other_question_types(question: str) -> None:
    assert is_list_all_articles_question(question) is False
