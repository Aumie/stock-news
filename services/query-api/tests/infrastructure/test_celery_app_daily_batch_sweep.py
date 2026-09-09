from __future__ import annotations

from unittest.mock import MagicMock, patch

from infrastructure.celery_app import (
    _run_sweep_on_beat_startup,
    celery_app,
    daily_batch_sweep_task,
)


class TestDailyBatchSweepSchedule:
    def test_beat_schedule_runs_daily_batch_sweep_every_24_hours(self) -> None:
        entry = celery_app.conf.beat_schedule["daily-batch-sweep"]
        assert entry["task"] == "daily_batch_sweep"
        assert entry["schedule"] == 60 * 60 * 24


class TestDailyBatchSweepTask:
    def test_calls_trigger_full_sweep_on_the_job_trigger(self) -> None:
        with patch("infrastructure.celery_app._job_trigger") as mock_trigger:
            daily_batch_sweep_task.run()

        mock_trigger.trigger_full_sweep.assert_called_once()

    def test_does_not_raise_when_no_job_trigger_is_configured(self) -> None:
        with patch("infrastructure.celery_app._job_trigger", None):
            daily_batch_sweep_task.run()  # does not raise


class TestRunSweepOnBeatStartup:
    def test_enqueues_the_sweep_task_when_beat_starts(self) -> None:
        with patch.object(daily_batch_sweep_task, "delay") as mock_delay:
            _run_sweep_on_beat_startup(sender=MagicMock())

        mock_delay.assert_called_once()
