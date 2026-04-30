#!/bin/bash
# 清理解题数据（测试循环专用）
# 新结构：output/{subject}/{platform}/data_*.json 和 output/{subject}/combined_latest.json

ENGINE_DIR="APP/engine"
ENGINE_OUTPUT="$ENGINE_DIR/output"
DEDUP_DB="$ENGINE_DIR/dedup.db"

echo "[clean] 清理运行产物..."

# 删除 output/ 下所有事项子目录（保留 output/ 本身）
if [ -d "$ENGINE_OUTPUT" ]; then
    # 删除所有子目录（事项目录）
    for item in "$ENGINE_OUTPUT"/*/; do
        if [ -d "$item" ]; then
            echo "  删除事项目录: $item"
            rm -rf "$item"
        fi
    done
fi

# 删除去重数据库
if [ -f "$DEDUP_DB" ]; then
    echo "  删除去重数据库: $DEDUP_DB"
    rm -f "$DEDUP_DB"
fi

echo "[clean] 完成。"
echo "  output/  : $(ls -la "$ENGINE_OUTPUT" 2>/dev/null | grep -c '^d' || echo 0) 个事项目录（应为 0）"
echo "  dedup.db : $([ -f "$DEDUP_DB" ] && echo '存在' || echo '已删除')"
