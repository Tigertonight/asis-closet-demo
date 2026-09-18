import asyncio
import threading

import anyio

from app import photo_work


def test_image_workers_are_bounded_without_blocking_event_loop(monkeypatch):
    async def scenario():
        monkeypatch.setattr(photo_work, "_workers", anyio.CapacityLimiter(2))
        release = threading.Event()
        lock = threading.Lock()
        active = peak = started = 0

        def work():
            nonlocal active, peak, started
            with lock:
                active += 1
                started += 1
                peak = max(peak, active)
            assert release.wait(5)
            with lock:
                active -= 1

        tasks = [asyncio.create_task(photo_work.run_photo_work(work)) for _ in range(8)]
        try:
            for _ in range(100):
                await asyncio.sleep(.01)
                if started == 2:
                    break
            assert started == 2
            # The event loop remains responsive while both CPU workers are busy.
            await asyncio.wait_for(asyncio.sleep(.02), .5)
            assert started == 2
        finally:
            release.set()
            await asyncio.gather(*tasks)
        assert peak == 2
        assert started == 8
    asyncio.run(scenario())


def test_admission_limits_upload_reads(monkeypatch):
    async def scenario():
        monkeypatch.setattr(photo_work, "_admission", anyio.CapacityLimiter(2))
        release = asyncio.Event()
        entered = 0
        async def upload():
            nonlocal entered
            async with photo_work.photo_admission():
                entered += 1
                await release.wait()
        tasks = [asyncio.create_task(upload()) for _ in range(8)]
        await asyncio.sleep(.02)
        assert entered == 2
        tasks[-1].cancel()
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert isinstance(results[-1], asyncio.CancelledError)
        assert entered == 7
        assert photo_work._admission.borrowed_tokens == 0
    asyncio.run(scenario())
