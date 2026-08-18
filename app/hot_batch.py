# -*- coding: utf-8 -*-
"""素材工场：热点角色 → 自动找参考图 → 批量生成拼豆图纸（保留角色特征）
流程: 热点词 → B站搜索参考图 → 下载封面 → 调现有管线(S1-S9)出图 → 多风格
"""
import os
import sys
import json
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hotspot
from pipeline.run import run_order

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOT_GALLERY = os.path.join(BASE_DIR, "hot_gallery.json")

def download_image(url, save_path, timeout=20):
    """下载参考图（处理 // 协议相对 URL）"""
    if url.startswith("//"):
        url = "https:" + url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        if len(data) < 1000:
            return False
        with open(save_path, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False

def get_reference(keyword, save_dir):
    """为热点词找参考图并下载，返回本地路径或 None"""
    os.makedirs(save_dir, exist_ok=True)
    refs = hotspot.search_bili_ref(keyword, limit=6)
    for i, ref in enumerate(refs):
        path = os.path.join(save_dir, f"ref_{i}.jpg")
        if download_image(ref["pic"], path):
            return path
    # 兜底：直接尝试已知 IP 关键词搜索
    return None

def generate_hot_order(keyword, character, ref_path, style="classic", tier="主力款",
                       orders_root=None, do_qc=True, subject=None):
    """为热点角色生成一张图纸，返回结果"""
    subject = subject or character or keyword
    res = run_order(ref_path, tier_key=tier, style_id=style, subject=subject,
                    title=f"{character or keyword}拼豆图纸", do_qc=do_qc,
                    orders_root=orders_root)
    return res

def generate_multi_style(keyword, character, ref_path, styles=("classic", "chibi_pastel", "retro8bit"),
                         tier="主力款", orders_root=None, do_qc=True):
    """多风格批量出图（热点角色 → 多风格图纸包）"""
    results = []
    for style in styles:
        res = generate_hot_order(keyword, character, ref_path, style=style,
                                 tier=tier, orders_root=orders_root, do_qc=do_qc)
        results.append({"style": style, **res})
        time.sleep(1)
    return results

# ---- 热点图纸画廊 ----
def load_gallery():
    if os.path.exists(HOT_GALLERY):
        try:
            with open(HOT_GALLERY, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"items": []}

def save_gallery(items):
    with open(HOT_GALLERY, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now().isoformat(), "items": items}, f, ensure_ascii=False, indent=2)

def add_to_gallery(entry):
    g = load_gallery()
    g["items"].insert(0, entry)
    g["items"] = g["items"][:60]  # 保留最近 60 条
    save_gallery(g["items"])
    return g

def process_hotspot(item, styles=("classic", "chibi_pastel"), orders_root=None):
    """处理一个热点：找参考图 → 多风格出图 → 加入画廊"""
    keyword = item["word"]
    character = item.get("character", "") or keyword
    # 1. 找参考图
    ref_dir = os.path.join(BASE_DIR, "samples", "hot_refs", datetime.now().strftime("%Y%m%d"))
    ref_path = get_reference(keyword, ref_dir)
    if not ref_path:
        return {"success": False, "keyword": keyword, "error": "未找到参考图"}
    # 2. 多风格出图
    results = generate_multi_style(keyword, character, ref_path, styles=styles,
                                   orders_root=orders_root)
    # 3. 收集画廊条目（取每个风格的主图/预览/zip）
    entry = {
        "keyword": keyword, "character": character, "created": datetime.now().isoformat(),
        "source": item.get("source", ""), "heat": item.get("heat", 0),
        "reason": item.get("reason", ""),
        "styles": [],
    }
    for r in results:
        if r.get("success"):
            entry["styles"].append({
                "style": r["style"], "order_id": r["order_id"],
                "grid": r.get("grid"), "colors": r.get("colors"),
                "zip": r.get("zip"), "qc": (r.get("qc") or {}).get("passed"),
            })
    if entry["styles"]:
        add_to_gallery(entry)
        return {"success": True, "entry": entry, "ref_path": ref_path}
    return {"success": False, "keyword": keyword, "error": "出图失败", "results": results}

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", required=True, help="热点词/角色名")
    ap.add_argument("--character", default="", help="角色名")
    ap.add_argument("--styles", default="classic,chibi_pastel", help="逗号分隔风格")
    args = ap.parse_args()
    item = {"word": args.keyword, "character": args.character, "heat": 0, "source": "手动"}
    res = process_hotspot(item, styles=tuple(s.strip() for s in args.styles.split(",")))
    print(json.dumps(res, ensure_ascii=False, indent=2))
