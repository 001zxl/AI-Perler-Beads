# -*- coding: utf-8 -*-
"""监听文件夹模式：往 watch_dir 丢一张图，自动生成交付包（串行队列防打爆配额）
用法: python3 -m app.watch --dir /path/to/inbox --tier 主力款 --style classic
"""
import sys
import os
import time
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from pipeline.run import run_order

def watch(inbox, tier, style, width, colors, colorcard, subject, qc, poll=5):
    os.makedirs(inbox, exist_ok=True)
    processed = set()
    print(f"👀 监听 {inbox} (轮询 {poll}s)，丢图自动生成... Ctrl+C 退出")
    print(f"   档位={tier} 风格={style} 色卡={colorcard}")
    while True:
        try:
            for fn in sorted(os.listdir(inbox)):
                if fn.startswith(".") or fn in processed:
                    continue
                full = os.path.join(inbox, fn)
                if not os.path.isfile(full):
                    continue
                ext = os.path.splitext(fn)[1].lower()
                if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                    processed.add(fn)
                    continue
                print(f"📥 检测到 {fn}，开始生成...")
                res = run_order(full, tier_key=tier, style_id=style, width=width,
                                max_colors=colors, colorcard=colorcard, subject=subject,
                                do_qc=qc)
                if res["success"]:
                    print(f"✅ {fn} → {res['order_id']} ({res['grid']}, {res['colors']}色)")
                else:
                    print(f"❌ {fn} 失败: {res.get('error')}")
                processed.add(fn)
        except KeyboardInterrupt:
            print("\n退出监听。")
            break
        except Exception as e:
            print(f"⚠️ {e}")
        time.sleep(poll)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(config.ORDERS_DIR, "inbox"), help="监听目录")
    ap.add_argument("--tier", default="主力款")
    ap.add_argument("--style", default="classic")
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--colors", type=int, default=None)
    ap.add_argument("--colorcard", default="mard")
    ap.add_argument("--subject", default="宠物")
    ap.add_argument("--qc", action="store_true")
    ap.add_argument("--poll", type=int, default=5)
    args = ap.parse_args()
    watch(args.dir, args.tier, args.style, args.width, args.colors, args.colorcard, args.subject, args.qc, args.poll)
