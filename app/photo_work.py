"""Dedicated image-work budget, independent of Starlette's shared thread limit.

Limit admission before reading uploads as well as CPU workers. Keep session JSON
transactions on the request thread; only pass immutable inputs to these workers.
"""
from functools import partial

import anyio

from app.ops import env_int

PHOTO_WORKERS = max(1, min(4, env_int("SELFIT_PHOTO_WORKERS", 2)))
_workers = anyio.CapacityLimiter(PHOTO_WORKERS)
_admission = anyio.CapacityLimiter(PHOTO_WORKERS)


def photo_admission():
    return _admission


async def run_photo_work(func, *args, **kwargs):
    # Default cancellation shielding keeps capacity held until the worker exits.
    return await anyio.to_thread.run_sync(partial(func, *args, **kwargs), limiter=_workers)
