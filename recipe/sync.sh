#!/bin/sh
# 把这份配方（本目录 = 上游仓库 blender-cli-android 的 recipe/）同步到组件市场仓库：
#
#   sh recipe/sync.sh ../cccodroid-components
#
# 规矩（见市场仓库 .claude/skills/component-authoring/SKILL.md）：
# 大组件的脚本改**上游仓库**，再 sync 过来；直接改市场里的副本，下次 sync 会被覆盖。
set -e
SRC=$(cd "$(dirname "$0")" && pwd)
[ $# -ge 1 ] || { echo "用法: sh recipe/sync.sh <组件市场仓库路径>"; exit 2; }
[ -d "$1" ] || { echo "找不到市场仓库：$1"; exit 2; }
DST="$1/recipes/blender"

mkdir -p "$DST"
rm -rf "$DST/bin" "$DST/lib" "$DST/skill"
cp -a "$SRC/recipe.json" "$SRC/bin" "$SRC/lib" "$SRC/skill" "$DST/"
echo "已同步 → $DST"
find "$DST" -type f | sed "s|$DST/|  |" | sort
