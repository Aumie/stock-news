from unittest.mock import MagicMock, patch

import pytest

from infrastructure.cloud_run_job_trigger import CloudRunJobTrigger


@pytest.fixture(autouse=True)
def _mock_google_auth():
    with patch("infrastructure.cloud_run_job_trigger.google.auth.default", return_value=(MagicMock(), None)):
        yield


def _make_trigger() -> CloudRunJobTrigger:
    with patch("infrastructure.cloud_run_job_trigger.AuthorizedSession") as mock_session_cls:
        trigger = CloudRunJobTrigger(project_id="stock-news-509321", region="us-central1")
        return trigger, mock_session_cls.return_value


def test_trigger_for_symbol_posts_to_the_run_endpoint_with_a_symbol_override():
    trigger, mock_session = _make_trigger()
    mock_session.post.return_value.raise_for_status.return_value = None

    trigger.trigger_for_symbol("TSLA")

    mock_session.post.assert_called_once_with(
        "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/"
        "namespaces/stock-news-509321/jobs/daily-batch:run",
        json={"overrides": {"containerOverrides": [{"args": ["--symbol", "TSLA"]}]}},
        timeout=10.0,
    )


def test_trigger_full_sweep_posts_to_the_run_endpoint_with_no_overrides():
    trigger, mock_session = _make_trigger()
    mock_session.post.return_value.raise_for_status.return_value = None

    trigger.trigger_full_sweep()

    mock_session.post.assert_called_once_with(
        "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/"
        "namespaces/stock-news-509321/jobs/daily-batch:run",
        json={},
        timeout=10.0,
    )


def test_trigger_for_symbol_does_not_raise_when_the_request_fails():
    trigger, mock_session = _make_trigger()
    mock_session.post.side_effect = ConnectionError("boom")

    trigger.trigger_for_symbol("TSLA")  # does not raise


def test_trigger_for_symbol_does_not_raise_on_a_non_2xx_response():
    trigger, mock_session = _make_trigger()
    mock_session.post.return_value.raise_for_status.side_effect = Exception("403 Forbidden")

    trigger.trigger_for_symbol("TSLA")  # does not raise
