# -*- coding: utf-8 -*-
"""每日自动化任务（crontab 调用）:
1. 刷新热点（微博+B站 → AI 过滤）
2. 对前 N 个热点批量出图（经典+Q版 2 风格）
3. 为画廊新条目生成引流内容包
用法: python3 -m app.run_daily [--limit 3] [--styles classic,chibi_pastel] [--log]
"""
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hotspot
import hot_batch
import hot_content

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3, help="批量出图的热点数")
    ap.add_argument("--styles", default="classic,chibi_pastel")
    ap.add_argument("--skip-gen", action="store_true", help="只刷新热点不批量出图")
    args = ap.parse_args()

    styles = tuple(s.strip() for s in args.styles.split(","))

    # 1. 刷新热点
    log("抓取热点中…")
    items = hotspot.collect_hotspots(use_ai_filter=True)
    log(f"热点刷新完成: {len(items)} 条动漫/影视/角色类")

    if args.skip_gen:
        return

    # 2. 批量出图（前 N 个，避免消耗过多配额）
    gallery_before = len(hot_batch.load_gallery().get("items", []))
    for i, item in enumerate(items[:args.limit]):
        keyword = item.get("word", "")
        if not keyword:
            continue
        log(f"[{i+1}/{min(len(items), args.limit)}] 出图: {keyword} ({item.get('character','')})")
        try:
            res = hot_batch.process_hotspot(item, styles=styles)
            if res.get("success"):
                log(f"  ✅ {len(res['entry']['styles'])} 风格完成")
            else:
                log(f"  ⚠️ {res.get('error', '失败')}")
        except Exception as e:
            log(f"  ❌ {e}")

    # 3. 为新条目生成内容包
    gallery = hot_batch.load_gallery()
    items_now = gallery.get("items", [])
    log(f"画廊现有 {len(items_now)} 条，生成本轮内容包…")
    content_results = hot_content.build_all_content(limit=len(items_now))
    log(f"内容包生成: {len(content_results)} 个 → hot_content/")

    # 4. 汇总
    summary = {
        "time": datetime.now().isoformat(),
        "hotspots": len(items),
        "hot_words": [it["word"] for it in items[:args.limit]],
        "gallery_total": len(items_now),
        "content_packs": len(content_results),
    }
    summary_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "daily_report.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    log(f"完成 → daily_report.json")

if __name__ == "__main__":
    main()
