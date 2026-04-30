#!/bin/bash
# 清理解题数据（测试循环专用）

ENGINE_OUTPUT="APP/engine/output"
DEDUP_DB="APP/engine/dedup.db"

echo "[clean] 清理运行产物..."

# 删除各规则目录下的原始采集数据
find "$ENGINE_OUTPUT" -name "data_*.json" -type f -delete 2>/dev/null

# 删除合并汇总文件和状态文件（精确列名，防止 glob 扩展失败）
rm -f "$ENGINE_OUTPUT/combined_latest.json" \
       "$ENGINE_OUTPUT/combined_20260429.json" \
       "$ENGINE_OUTPUT/state.json" \
       "$ENGINE_OUTPUT/cninfo_data_value_*.json" \
       "$ENGINE_OUTPUT/tmtpost_data_articles_*.json"

# 删除去重数据库
rm -f "$DEDUP_DB"

echo "[clean] 完成。当前状态："
echo "  output/    : $(ls "$ENGINE_OUTPUT" 2>/dev/null | wc -l) 个文件/目录"
echo "  dedup.db   : $([ -f "$DEDUP_DB" ] && echo '存在' || echo '已删除')"
