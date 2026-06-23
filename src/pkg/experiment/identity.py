"""实验事实的确定性身份键。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_annotation_id(
    *,
    experiment_id: str,
    target_type: str,
    target: str,
    attribute: str,
    value: Any,
    source: str,
) -> str:
    """相同事实重跑得到同一 ID，使 MySQL upsert 真正幂等。"""

    canonical = json.dumps(
        {
            "experiment_id": experiment_id,
            "target_type": target_type,
            "target": target,
            "attribute": attribute,
            "value": value,
            "source": source,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"ann_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]}"


__all__ = ["stable_annotation_id"]
