from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.startup import _exit_if_all_failed_definitively, retry_degraded_instances


def _unit(ready=False, failure_kind=None, arr_type=None, setup_result=False):
    unit = MagicMock()
    unit.ready = ready
    unit.failure_kind = failure_kind
    unit.name = "Unit"
    unit.base_url = "http://unit"
    unit.last_error = "some error"
    unit.setup_tip = "💡 Tip: fix it"
    unit.arr_type = arr_type
    unit.setup = AsyncMock(return_value=setup_result)
    return unit


def _settings(instances=None, qbits=None, sabnzbds=None):
    settings = MagicMock()
    settings.instances = instances or []
    settings.download_clients.qbittorrent = qbits or []
    settings.download_clients.sabnzbd = sabnzbds or []
    settings.jobs.detect_deletions.enabled = True
    return settings


def test_exit_when_all_units_failed_definitively():
    settings = _settings(
        instances=[_unit(failure_kind="definitive")],
        qbits=[_unit(failure_kind="definitive")],
    )

    with patch("src.utils.startup.wait_and_exit") as mock_exit:
        _exit_if_all_failed_definitively(settings)

    mock_exit.assert_called_once()


def test_no_exit_when_one_unit_failed_transiently():
    settings = _settings(
        instances=[_unit(failure_kind="definitive"), _unit(failure_kind="transient")],
    )

    with patch("src.utils.startup.wait_and_exit") as mock_exit:
        _exit_if_all_failed_definitively(settings)

    mock_exit.assert_not_called()


def test_no_exit_when_one_unit_is_healthy():
    settings = _settings(
        instances=[_unit(ready=True), _unit(failure_kind="definitive")],
    )

    with patch("src.utils.startup.wait_and_exit") as mock_exit:
        _exit_if_all_failed_definitively(settings)

    mock_exit.assert_not_called()


@pytest.mark.asyncio
async def test_retry_skips_ready_and_definitive_units(caplog):
    ready_unit = _unit(ready=True)
    definitive_unit = _unit(failure_kind="definitive")
    settings = _settings(instances=[ready_unit, definitive_unit])

    with caplog.at_level("ERROR"):
        await retry_degraded_instances(settings)

    ready_unit.setup.assert_not_awaited()
    definitive_unit.setup.assert_not_awaited()
    assert any("configuration error" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_retry_rejoins_transient_arr_and_sets_up_watchers():
    arr = _unit(failure_kind="transient", arr_type="sonarr", setup_result=True)
    settings = _settings(instances=[arr])
    watch_manager = MagicMock()
    watch_manager.setup_for_arr = AsyncMock()

    await retry_degraded_instances(settings, watch_manager)

    arr.setup.assert_awaited_once()
    watch_manager.setup_for_arr.assert_awaited_once_with(arr)


@pytest.mark.asyncio
async def test_retry_logs_warning_when_still_failing(caplog):
    arr = _unit(failure_kind="transient", arr_type="sonarr", setup_result=False)
    settings = _settings(instances=[arr])
    watch_manager = MagicMock()
    watch_manager.setup_for_arr = AsyncMock()

    with caplog.at_level("WARNING"):
        await retry_degraded_instances(settings, watch_manager)

    arr.setup.assert_awaited_once()
    watch_manager.setup_for_arr.assert_not_awaited()
    assert any("will retry next cycle" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_retry_exits_when_everything_becomes_definitive():
    """If the only units are definitively failed, the per-cycle retry exits."""
    settings = _settings(instances=[_unit(failure_kind="definitive")])

    with patch("src.utils.startup.wait_and_exit") as mock_exit:
        await retry_degraded_instances(settings)

    mock_exit.assert_called_once()
