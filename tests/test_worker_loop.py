from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.loop import WorkerLoop


@pytest.mark.asyncio
async def test_worker_continues_after_tick_error(caplog):
    loop = WorkerLoop()
    session_context = MagicMock()
    session_context.__enter__.return_value = object()
    calls = 0

    def refresh(_db):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database error")
        loop.stop()

    with (
        patch("app.worker.loop.SessionLocal", return_value=session_context),
        patch.object(loop, "_refresh_job_gauges", side_effect=refresh),
        patch("app.worker.loop.claim_next_pending_job", return_value=None),
        patch("app.worker.loop.asyncio.sleep", new_callable=AsyncMock),
    ):
        await loop.run()

    assert calls == 2
    assert "snapshot_worker_tick_failed" in caplog.text
