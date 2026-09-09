#!/usr/bin/env bash
# ai-daily 环境自检 & 自动安装
# 在 skill 首次运行前由 agent 调用，确保所有依赖就绪
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok=0
check_cmd() {
    if command -v "$1" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "  ${RED}✗${NC} $1 (未安装)"
        return 1
    fi
}

check_py_pkg() {
    if python3 -c "import $1" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Python: $1"
        return 0
    else
        echo -e "  ${YELLOW}⚠${NC} Python: $1 (缺失，尝试安装...)"
        python3 -m pip install "$2" --quiet 2>/dev/null && echo -e "    ${GREEN}→ 已安装 $2${NC}" && return 0
        echo -e "    ${RED}→ 安装失败${NC}"
        return 1
    fi
}

echo "═══════════════════════════════════════"
echo "  AI Daily News - 环境自检"
echo "═══════════════════════════════════════"
echo ""

echo "[系统工具]"
check_cmd python3 || ok=1
python3 -m pip --version >/dev/null 2>&1 || {
    echo -e "  ${RED}✗${NC} python3 -m pip (不可用)"
    ok=1
}

echo ""
echo "[Python 依赖]"
check_py_pkg requests requests || ok=1
echo ""
echo "[目录检查]"
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
for f in ai_daily.py run_daily.sh sources.json README.md; do
    if [ -f "$SKILL_DIR/$f" ]; then
        echo -e "  ${GREEN}✓${NC} $f"
    else
        echo -e "  ${RED}✗${NC} $f (缺失!)"
        ok=1
    fi
done

echo ""
echo "[输出目录]"
mkdir -p "$SKILL_DIR/output/crawl" && echo -e "  ${GREEN}✓${NC} $SKILL_DIR/output/crawl/"
mkdir -p "$SKILL_DIR/output/logs" && echo -e "  ${GREEN}✓${NC} $SKILL_DIR/output/logs/"

echo ""
if [ $ok -eq 0 ]; then
    echo -e "${GREEN}环境检查通过，可以运行。${NC}"
else
    echo -e "${RED}环境检查有缺失项，请手动修复后重试。${NC}"
fi
echo ""
exit $ok
