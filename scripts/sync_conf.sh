#!/usr/bin/env bash
# 同步 roco_kingdom_world_conf 游戏配置数据到最新
set -euo pipefail

cd "$(dirname "$0")/.."
git submodule update --remote roco_kingdom_world_conf
