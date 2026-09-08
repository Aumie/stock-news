from unittest.mock import patch

from infrastructure.local_docker_job_trigger import LocalDockerJobTrigger


def test_trigger_for_symbol_invokes_docker_compose_run_scoped_to_symbol():
    trigger = LocalDockerJobTrigger(project_name="stock-news")

    with patch("infrastructure.local_docker_job_trigger.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        trigger.trigger_for_symbol("TSLA")

    args = mock_run.call_args.args[0]
    assert args == [
        "docker",
        "compose",
        "-f",
        "/workspace/docker-compose.yml",
        "-p",
        "stock-news",
        "--profile",
        "batch",
        "run",
        "--rm",
        "daily-batch",
        "--symbol",
        "TSLA",
    ]


def test_trigger_for_symbol_uses_given_service_name():
    trigger = LocalDockerJobTrigger(project_name="stock-news", service="custom-batch")

    with patch("infrastructure.local_docker_job_trigger.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        trigger.trigger_for_symbol("AAPL")

    assert "custom-batch" in mock_run.call_args.args[0]


def test_trigger_for_symbol_does_not_raise_when_docker_command_fails():
    trigger = LocalDockerJobTrigger(project_name="stock-news")

    with patch("infrastructure.local_docker_job_trigger.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "some docker error"

        trigger.trigger_for_symbol("TSLA")  # does not raise
