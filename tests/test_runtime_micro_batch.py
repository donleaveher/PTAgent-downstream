"""pkg.runtime.micro_batch — MCP 侧 micro-batch 合并（与 ``MicroBatcher`` 实现一致）。"""

from __future__ import annotations

import concurrent.futures

from pkg.runtime.micro_batch import MicroBatcher


def test_microbatcher_merges_parallel_submits() -> None:
    batch_sizes: list[int] = []

    def fn(xs: list[int]) -> list[int]:
        batch_sizes.append(len(xs))
        return [x * 2 for x in xs]

    b = MicroBatcher(fn, max_batch=8, max_wait_s=0.15)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(b.submit, i) for i in range(6)]
        outs = [f.result(timeout=5.0) for f in futs]

    assert sorted(outs) == [i * 2 for i in range(6)]
    assert sum(batch_sizes) == 6
    assert len(batch_sizes) <= 3
