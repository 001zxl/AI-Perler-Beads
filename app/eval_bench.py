# -*- coding: utf-8 -*-
"""拼豆图纸质量评测集 + 评分表
基准样本: 宠物/真人/动漫/Logo/风景 各若干张
每张生成: 免费工具版(skip_ai=普通量化) / AI版(完整管线) / 诊断报告
输出: eval_report.csv 评分表（清晰度/孤立点/色数/五官/可拼性）
"""
import os
import sys
import csv
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from pipeline.run import run_order
from pipeline.quantize import quantize_grid, global_quantize, bfs_cleanup, remove_isolated_pixels
from pipeline.colormap import OklabColorMapper
from pipeline.scorability import score_pattern

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(BASE_DIR, "eval_set")

# 评测集结构: eval_set/<类型>/<样本名>.jpg
def ensure_eval_dirs():
    for t in ["宠物", "真人", "动漫", "Logo", "风景"]:
        os.makedirs(os.path.join(EVAL_DIR, t), exist_ok=True)
    return EVAL_DIR

def collect_samples():
    """收集 eval_set 下所有样本: [(类型, 路径), ...]"""
    samples = []
    for t in ["宠物", "真人", "动漫", "Logo", "风景"]:
        d = os.path.join(EVAL_DIR, t)
        if not os.path.exists(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                samples.append((t, os.path.join(d, f), f))
    return samples

def eval_one(img_type, img_path, name, out_dir=None, do_ai=True):
    """评测一张图，返回诊断数据
    do_ai=True: 完整管线（AI重绘+轮廓+保护）
    do_ai=False: 纯代码（免费工具等效：直接量化）
    """
    if do_ai:
        res = run_order(img_path, tier_key="主力款", style_id="classic",
                        subject=name, do_qc=False)
        return res
    else:
        # 免费工具等效：直接量化无AI
        from PIL import Image
        img = Image.open(img_path).convert("RGB")
        g, W, H = quantize_grid(img, 60, "auto", 12, use_dominant=True)
        if len(set(g)) > 12:
            g = global_quantize(g, 12)
        g = bfs_cleanup(g, W, H, threshold=18)
        g2, _ = remove_isolated_pixels(g, W, H)
        sc = score_pattern(g2, W, H, 12)
        return {"success": True, "grid": f"{W}x{H}", "colors": len(set(g2)),
                "scorability": sc, "img_type": img_type}

def run_eval(limit_per_type=3, do_ai=True):
    """跑评测集，输出 CSV 评分表"""
    ensure_eval_dirs()
    samples = collect_samples()
    if not samples:
        return {"success": False, "error": f"评测集为空，请先放图片到 {EVAL_DIR}/<类型>/"}
    rows = []
    for img_type, path, name in samples[:limit_per_type * 5]:
        try:
            res = eval_one(img_type, path, os.path.splitext(name)[0], do_ai=do_ai)
            sc = res.get("scorability", {})
            rows.append({
                "类型": img_type, "样本": name,
                "网格": res.get("grid", "?"), "色数": res.get("colors", "?"),
                "可拼性分": sc.get("score", "?"), "判定": sc.get("verdict", "?"),
                "孤立点%": sc.get("isolated_ratio", "?"),
            })
        except Exception as e:
            rows.append({"类型": img_type, "样本": name, "网格": "ERR", "色数": str(e)[:20], "可拼性分": "", "判定": "", "孤立点%": ""})
    # 写 CSV
    csv_path = os.path.join(BASE_DIR, "docs", f"eval_report_{'AI' if do_ai else '免费工具'}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["类型", "样本", "网格", "色数", "可拼性分", "判定", "孤立点%"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return {"success": True, "count": len(rows), "csv": csv_path, "rows": rows}

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai", action="store_true", help="用完整AI管线评测")
    ap.add_argument("--free", action="store_true", help="用免费工具等效(纯量化)评测")
    ap.add_argument("--limit", type=int, default=3, help="每类型样本数")
    args = ap.parse_args()
    if args.free:
        r = run_eval(args.limit, do_ai=False)
    else:
        r = run_eval(args.limit, do_ai=True)
    print(json.dumps(r, ensure_ascii=False, indent=1)[:800])
