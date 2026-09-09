#!/usr/bin/env bash
# ai-daily 模块一一键运行脚本
# 用法: ./run_daily.sh [morning|evening] [ai_daily.py 的其他参数]
# 流程: 环境检查 -> 宽口径爬取 AI 产业候选新闻 -> 输出 json/md/txt 交接文件
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
EDITION="${1:-morning}"
if [ "$#" -gt 0 ]; then
    shift
fi
DATE=$(date +%Y-%m-%d)
OUTPUT_BASE="$SKILL_DIR/output/crawl"
LOG="$SKILL_DIR/output/logs/ai_daily.log"
EXTRA_ARGS=("$@")

for ((i = 0; i < ${#EXTRA_ARGS[@]}; i++)); do
    case "${EXTRA_ARGS[$i]}" in
        --output-dir)
            if ((i + 1 >= ${#EXTRA_ARGS[@]})); then
                echo "--output-dir 缺少目录参数"
                exit 1
            fi
            OUTPUT_BASE="${EXTRA_ARGS[$((i + 1))]}"
            ;;
        --output-dir=*)
            OUTPUT_BASE="${EXTRA_ARGS[$i]#--output-dir=}"
            ;;
    esac
done
case "$OUTPUT_BASE" in
    /*) ;;
    *) OUTPUT_BASE="$PWD/$OUTPUT_BASE" ;;
esac
OUTPUT_DIR="$OUTPUT_BASE/$DATE"

if [ "$EDITION" != "morning" ] && [ "$EDITION" != "evening" ]; then
    echo "用法: $0 [morning|evening]"
    exit 1
fi

mkdir -p "$(dirname "$LOG")"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "=== AI Daily 数据采集 ${EDITION} 开始 ==="

log "[1/2] 环境检查..."
bash "$SKILL_DIR/auto_init.sh" >> "$LOG" 2>&1 || {
    log "环境检查失败，中止"
    exit 1
}

log "[2/2] 宽口径爬取 AI 产业候选新闻..."
python3 -u "$SKILL_DIR/ai_daily.py" "$EDITION" "${EXTRA_ARGS[@]}" 2>&1 | tee -a "$LOG"

JSON_FILE="$OUTPUT_DIR/${DATE}_${EDITION}.json"
MD_FILE="$OUTPUT_DIR/${DATE}_${EDITION}.md"
TXT_FILE="$OUTPUT_DIR/${DATE}_${EDITION}.txt"

if [ ! -f "$JSON_FILE" ] || [ ! -f "$MD_FILE" ] || [ ! -f "$TXT_FILE" ]; then
    log "采集失败：未找到预期输出，请检查日志 $LOG"
    exit 1
fi

log "采集完成，交接文件如下："
log "JSON: $JSON_FILE"
log "Markdown: $MD_FILE"
log "TXT: $TXT_FILE"
log "说明：本模块不做 Top 10 截断；已做基础去重并保留跨平台来源，后续负责人可基于 JSON/TXT 清洗筛选。"
log "=== AI Daily 数据采集 ${EDITION} 完成 ==="
