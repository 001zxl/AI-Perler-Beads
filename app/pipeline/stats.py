# -*- coding: utf-8 -*-
"""S5 色卡与用量统计：图例 + 每色豆量 + 采购清单 CSV（+5% 备用）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
import csv
from render import _get_font

def compute_stats(grid_rgb, color_map, reserve_ratio=0.05):
    """统计每色号用量。返回 [(code, name, rgb, count, suggest), ...] 按用量降序"""
    from collections import Counter
    from render import _lookup
    cnt = Counter()
    for rgb in grid_rgb:
        code, name, orig, de = _lookup(color_map, rgb)
        cnt[code] += 1
    rows = []
    for code, count in cnt.most_common():
        c = color_map.colors[code]
        suggest = int(count * (1 + reserve_ratio)) + 1
        rows.append({
            "code": code, "name": c["name"], "rgb": c["rgb"],
            "count": count, "suggest": suggest,
        })
    return rows, sum(cnt.values())

def render_palette_sheet(rows, total, width, height, brand, reserve_ratio=0.05):
    """色卡统计图：色块图例 + 用量表 + 采购建议"""
    cell_w, cell_h = 480, 66
    pad = 24
    header_h = 130
    W = cell_w + pad * 2
    H = header_h + len(rows) * cell_h + pad * 2 + 140
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    t_font = _get_font(34, bold=True)
    s_font = _get_font(20)
    draw.text((pad, 18), "色卡与用量统计", fill="black", font=t_font)
    draw.text((pad, 70), f"色卡: {brand} | 总豆数: {total} 颗 | 网格: {width}×{height} | 颜色数: {len(rows)}",
              fill=(60, 60, 60), font=s_font)
    draw.text((pad, 100), f"采购建议 = 实际用量 × (1 + {int(reserve_ratio*100)}%) 备用",
              fill=(60, 60, 60), font=s_font)

    y = header_h
    for i, r in enumerate(rows):
        ry = y + i * cell_h
        # 色块
        draw.rectangle([pad, ry, pad + 46, ry + 36], fill=tuple(r["rgb"]), outline="black")
        # 色号 + 名称
        draw.text((pad + 56, ry + 2), f"{r['code']} {r['name']}", fill="black", font=_get_font(20))
        # 用量 + 建议
        draw.text((pad + 180, ry + 2), f"用量 {r['count']} 颗", fill="black", font=_get_font(20))
        draw.text((pad + 180, ry + 22), f"建议购买 {r['suggest']} 颗", fill=(90, 90, 90), font=_get_font(16))
    return img

def write_shopping_csv(rows, total, width, height, brand, path):
    """采购清单 CSV：色号/名称/实际数量/建议购买量"""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["色号", "颜色名称", "实际数量(颗)", "建议购买数量(颗,含5%备用)", "备注"])
        for r in rows:
            w.writerow([r["code"], r["name"], r["count"], r["suggest"], ""])
        w.writerow([])
        w.writerow(["总豆数", "", total, "", ""])
        w.writerow(["网格尺寸", f"{width}x{height}", "", "", ""])
        w.writerow(["参考色卡", brand, "", "", ""])
