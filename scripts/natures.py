"""性格加减属性只从 NATURE_CONF.json 读取。"""

from __future__ import annotations

import json
from pathlib import Path

# 配置里的属性效果编号。83 在界面上写成魔防，旧数据里的「魔抗」是同一个属性。
EFFECT_STATS = {
    79: "生命",
    80: "物攻",
    81: "魔攻",
    82: "物防",
    83: "魔防",
    84: "速度",
}


def nature_rows(conf_dir: str | Path) -> list[tuple[int, str, str, str]]:
    path = Path(conf_dir) / "NATURE_CONF.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for item in data:
        plus = EFFECT_STATS.get(item.get("positive_effect"))
        minus = EFFECT_STATS.get(item.get("negative_effect"))
        if not plus or not minus or plus == minus:
            continue
        rows.append((int(item["id"]), str(item.get("name") or ""), plus, minus))
    return rows


def seed_natures(cursor, conf_dir: str | Path) -> int:
    rows = nature_rows(conf_dir)
    if not rows:
        return 0
    cursor.executemany(
        "INSERT OR REPLACE INTO pet_natures (id, name, plus_stat, minus_stat) VALUES (?, ?, ?, ?)",
        rows,
    )
    return len(rows)
