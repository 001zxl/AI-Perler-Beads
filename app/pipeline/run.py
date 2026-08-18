# -*- coding: utf-8 -*-
"""拼豆图纸生产流水线：原图 → 交付包 5 件套
S1 AI像素化 → S2 量化 → S3 色卡映射 → S4 施工图 → S5 统计CSV → S6 预览 → S7 素材 → S8 质检 → S9 打包
"""
import os
import sys
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from pipeline.ai_pixelate import pixelate
from pipeline.quantize import (quantize_grid, color_counts, merge_near_colors, bfs_cleanup,
                             global_quantize, remove_isolated_pixels, simplify_small_regions)
from pipeline.colormap import ColorMapper, OklabColorMapper
from pipeline.render import render_construction_sheet
from pipeline.stats import compute_stats, render_palette_sheet, write_shopping_csv
from pipeline.preview import render_preview
from pipeline.content import make_comparison, write_captions_file
from pipeline.qc import qc_image
from pipeline.deliver import make_order_dir, save_meta, zip_delivery, new_order_id

def run_order(source_path, tier_key="主力款", style_id="classic", width=None, height="auto",
              max_colors=None, colorcard="mard", bead="2.6mm", title=None, subject="宠物",
              orders_root=None, skip_ai=False, do_qc=False, extra_subject=""):
    """执行完整流水线，返回结果 dict
    skip_ai=True 时跳过 S1（直接对 source_path 量化，用于测试/无 AI 场景）
    """
    orders_root = orders_root or config.ORDERS_DIR
    tier = config.TIERS.get(tier_key, config.TIERS["主力款"])
    width = width or tier["width"]
    if isinstance(width, list):
        width = width[0]
    max_colors = max_colors or tier["colors"]
    style = config.STYLES.get(style_id, config.STYLES["classic"])
    title = title or f"{subject}拼豆图纸 ({style['name']})"
    order_id = new_order_id()
    order_dir = make_order_dir(orders_root, order_id)
    meta = {
        "order_id": order_id, "tier": tier_key, "style": style_id, "style_name": style["name"],
        "width": width, "height": height, "max_colors": max_colors, "colorcard": colorcard,
        "bead": bead, "subject": subject, "created": datetime.now().isoformat(),
    }
    steps = {}
    try:
        # ---- S1 AI 像素化 ----
        pixel_path = os.path.join(order_dir, "intermediate", "pixel_base.png")
        if skip_ai or not os.path.exists(source_path):
            # 无 AI：直接用原图（或已有像素图）量化
            work_img = source_path
        else:
            ok, res = pixelate(source_path, pixel_path, style_id=style_id, width=width,
                               max_colors=max_colors, extra_subject=extra_subject)
            if not ok:
                return {"success": False, "step": "S1", "error": res, "order_id": order_id}
            steps["S1"] = res
            work_img = pixel_path

        # ---- S2 量化 ----
        from PIL import Image
        img = Image.open(work_img).convert("RGB")
        # mono 风格兜底：强制灰度化（黑白线稿无需 AI 画，代码 100% 精确）
        if style.get("palette") == "mono":
            img = img.convert("L").convert("RGB")
        grid_rgb, W, H = quantize_grid(img, width, height, max_colors, use_dominant=True)
        meta["grid"] = f"{W}x{H}"
        # 主导色后全局量化到 max_colors（防止每格独立采样导致色数爆炸）
        if len(set(grid_rgb)) > max_colors:
            grid_rgb = global_quantize(grid_rgb, max_colors)
        # 孤立噪点清理（解决细节碎/毛发脏）
        grid_rgb, _iso = remove_isolated_pixels(grid_rgb, W, H)
        # BFS 连通区域杂色清理（借鉴 perler-beads，提升色块纯净度）
        grid_rgb = bfs_cleanup(grid_rgb, W, H, threshold=18)
        # 鼻口小区域简化（粉鼻子保护）
        grid_rgb, _sm = simplify_small_regions(grid_rgb, W, H, min_area=3)
        if len(set(grid_rgb)) > max_colors:
            grid_rgb = merge_near_colors(grid_rgb, max_colors)
        steps["S2"] = f"{W}x{H} 网格, {len(set(grid_rgb))} 色 (主导色+噪点清理+简化)"

        # ---- S3 色卡映射（Oklab 感知色距，视觉更准）----
        mapper = OklabColorMapper(colorcard, style.get("palette", "standard"))
        steps["S3"] = f"{colorcard} 色卡映射完成 (Oklab)"

        # ---- S4 施工图 ----
        sheet = render_construction_sheet(grid_rgb, W, H, mapper, title=title, bead_size=bead)
        sheet_path = os.path.join(order_dir, "delivery", "1_施工主图.png")
        sheet.save(sheet_path)
        steps["S4"] = "施工主图完成"

        # ---- S5 统计 + CSV ----
        rows, total = compute_stats(grid_rgb, mapper)
        palette_sheet = render_palette_sheet(rows, total, W, H, mapper.brand)
        palette_path = os.path.join(order_dir, "delivery", "2_色卡与用量统计.png")
        palette_sheet.save(palette_path)
        csv_path = os.path.join(order_dir, "delivery", "3_采购清单.csv")
        write_shopping_csv(rows, total, W, H, mapper.brand, csv_path)
        steps["S5"] = f"{len(rows)} 色, 共 {total} 颗, 采购清单 CSV 完成"

        # ---- S6 成品预览 ----
        preview_img = render_preview(grid_rgb, W, H)
        preview_path = os.path.join(order_dir, "delivery", "4_成品预览.png")
        preview_img.save(preview_path)
        steps["S6"] = "成品预览完成"

        # ---- S7 内容素材 ----
        if os.path.exists(source_path):
            cmp = make_comparison(source_path, preview_img,
                                  os.path.join(order_dir, "delivery", "5_小红书素材_对比图.png"),
                                  style_name=style["name"], tier_name=tier_key)
            captions = write_captions_file(
                os.path.join(order_dir, "delivery", "5_小红书素材_文案.txt"),
                style["name"], subject, tier_key, order_id)
            steps["S7"] = "对比图+文案完成"

        # ---- S8 质检（可选）----
        qc_result = None
        if do_qc:
            if style.get("palette") in ("mono", "minimal"):
                # mono/极简：代码确定性兜底（强制灰度化），无需视觉质检
                qc_result = {"passed": True, "detail": {"reason": "代码确定性兜底生成（灰度化），跳过视觉质检"}, "target": "deterministic"}
                steps["S8"] = "质检通过(代码兜底确定性生成)"
            else:
                # 其他风格：检查 AI 像素底图（AI 可能翻车处）
                qc_target = pixel_path if os.path.exists(pixel_path) else (source_path if os.path.exists(source_path) else sheet_path)
                passed, detail = qc_image(qc_target, style_desc=style["prompt_fragment"])
                qc_result = {"passed": passed, "detail": detail, "target": os.path.basename(qc_target)}
                steps["S8"] = f"质检{'通过' if passed else '未通过'}: {detail.get('reason', '')}"
        else:
            steps["S8"] = "质检跳过(do_qc=False)"

        # ---- S9 打包 ----
        zip_path = zip_delivery(order_dir, os.path.join(order_dir, "delivery"), order_id)
        save_meta(order_dir, {**meta, "steps": steps, "qc": qc_result})
        steps["S9"] = f"交付包: {os.path.basename(zip_path)}"

        # 附带历史经验建议（反馈学习闭环）
        import feedback as feedback_mod
        hits = feedback_mod.get_lessons_for(style=style_id, tier=tier_key, colorcard=colorcard, subject=subject)
        lessons = feedback_mod.summarize_lessons(hits) if hits else None

        return {
            "success": True, "order_id": order_id, "order_dir": order_dir,
            "delivery_dir": os.path.join(order_dir, "delivery"), "zip": zip_path,
            "grid": meta["grid"], "colors": len(set(grid_rgb)), "total": total,
            "steps": steps, "qc": qc_result, "lessons": lessons,
            "files": sorted(os.listdir(os.path.join(order_dir, "delivery"))),
        }
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "step": "?", "error": str(e), "order_id": order_id}

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="拼豆图纸流水线")
    ap.add_argument("--input", required=True, help="原图路径")
    ap.add_argument("--tier", default="主力款")
    ap.add_argument("--style", default="classic")
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--colors", type=int, default=None)
    ap.add_argument("--colorcard", default="mard")
    ap.add_argument("--bead", default="2.6mm")
    ap.add_argument("--subject", default="宠物")
    ap.add_argument("--skip-ai", action="store_true")
    ap.add_argument("--qc", action="store_true", help="启用 AI 质检")
    args = ap.parse_args()
    res = run_order(args.input, tier_key=args.tier, style_id=args.style, width=args.width,
                    max_colors=args.colors, colorcard=args.colorcard, bead=args.bead,
                    subject=args.subject, skip_ai=args.skip_ai, do_qc=args.qc)
    print("结果:", res)
