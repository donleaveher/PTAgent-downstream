"""Micro-batching for expensive inference (reusable outside MCP)."""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future
from typing import Callable, Generic, TypeVar

T = TypeVar("T")
R = TypeVar("R")


class MicroBatcher(Generic[T, R]):
    """Collect single items into batches and invoke ``fn(list[T]) -> list[R]``."""

    def __init__(
        self,
        fn: Callable[[list[T]], list[R]],
        *,
        max_batch: int = 16,
        max_wait_s: float = 0.05,
    ) -> None:
        if max_batch < 1:
            raise ValueError("max_batch must be >= 1")
        if max_wait_s < 0:
            raise ValueError("max_wait_s must be >= 0")
        self._fn = fn
        self._max_batch = max_batch
        self._max_wait = max_wait_s
        self._q: queue.Queue[tuple[T, Future[R]]] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="MicroBatcher", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            x0, f0 = self._q.get()
            batch: list[tuple[T, Future[R]]] = [(x0, f0)]
            deadline = time.monotonic() + self._max_wait
            while len(batch) < self._max_batch:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                try:
                    batch.append(self._q.get(timeout=timeout))
                except queue.Empty:
                    break
            xs = [b[0] for b in batch]
            futures = [b[1] for b in batch]
            try:
                outs = self._fn(xs)
            except Exception as exc:  # noqa: BLE001
                for fut in futures:
                    if not fut.done():
                        fut.set_exception(exc)
                continue
            if not isinstance(outs, list) or len(outs) != len(xs):
                err = RuntimeError(
                    f"batch fn must return list of len {len(xs)}, got {type(outs).__name__}"
                )
                for fut in futures:
                    if not fut.done():
                        fut.set_exception(err)
                continue
            for fut, out in zip(futures, outs):
                if not fut.done():
                    fut.set_result(out)

    def submit(self, item: T) -> R:
        fut: Future[R] = Future()
        self._q.put((item, fut))
        return fut.result()


__all__ = ["MicroBatcher"]
