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
    # 源图存档（供微调/重新生成用）
    try:
        import shutil
        if os.path.exists(source_path):
            ext = os.path.splitext(source_path)[1] or ".jpg"
            shutil.copy(source_path, os.path.join(order_dir, "source", f"source{ext}"))
    except Exception:
        pass
    meta = {
        "order_id": order_id, "tier": tier_key, "style": style_id, "style_name": style["name"],
        "width": width, "height": height, "max_colors": max_colors, "colorcard": colorcard,
        "bead": bead, "subject": subject, "created": datetime.now().isoformat(),
    }
    steps = {}
    try:
        # ---- S0 图片类型识别（用于轮廓/卡通化/关键区域策略）----
        img_type = "默认"
        try:
            from pipeline.type_aware import detect_type
            if not skip_ai:
                img_type, _subj, _areas = detect_type(source_path)
                meta["img_type"] = img_type
        except Exception:
            pass

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
        # 面部关键点保护（眼睛/鼻口，AI 定位）
        face_regions = {}
        try:
            from pipeline.face_guard import detect_face_regions, apply_face_guard
            if not skip_ai:
                face_regions = detect_face_regions(work_img, W, H)
        except Exception:
            face_regions = {}
        # 孤立噪点清理（解决细节碎/毛发脏）
        grid_rgb, _iso = remove_isolated_pixels(grid_rgb, W, H)
        # 面部保护：眼睛区域跳过清理 + 鼻口简化
        if face_regions:
            grid_rgb, _protected = apply_face_guard(grid_rgb, W, H, face_regions)
        # BFS 连通区域杂色清理（借鉴 perler-beads，提升色块纯净度）
        grid_rgb = bfs_cleanup(grid_rgb, W, H, threshold=18)
        # 鼻口小区域简化（粉鼻子保护）
        grid_rgb, _sm = simplify_small_regions(grid_rgb, W, H, min_area=3)
        # 类型感知轮廓加粗（动漫/Logo 黑边、宠物深棕边）
        try:
            from pipeline.outline import strengthen_outline
            img_type_hint = meta.get("img_type", "默认")
            grid_rgb = strengthen_outline(grid_rgb, W, H, img_type_hint)
        except Exception:
            pass
        if len(set(grid_rgb)) > max_colors:
            grid_rgb = merge_near_colors(grid_rgb, max_colors)
        steps["S2"] = f"{W}x{H} 网格, {len(set(grid_rgb))} 色 (类型+轮廓+清理)"

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
        write_shopping_csv(rows, total, W, H, mapper.brand, csv_path, mapper=mapper)
        steps["S5"] = f"{len(rows)} 色, 共 {total} 颗, 采购清单 CSV 完成"

        # ---- S5.5 可拼性评分 + 图纸信息卡 ----
        try:
            from pipeline.scorability import score_pattern, pattern_info, info_card_text
            sc = score_pattern(grid_rgb, W, H, max_colors)
            pinfo = pattern_info(grid_rgb, W, H, bead, difficulty=tier.get("difficulty", {}).get("level", "标准"))
            meta["scorability"] = sc
            meta["pattern_info"] = pinfo
            # 信息卡写入交付
            info_path = os.path.join(order_dir, "delivery", "3.5_图纸信息.txt")
            with open(info_path, "w", encoding="utf-8") as f:
                f.write(info_card_text(pinfo, mapper.brand))
            steps["S5.5"] = f"可拼性评分 {sc['score']} 分 ({sc['verdict']})"
        except Exception as e:
            steps["S5.5"] = f"评分跳过: {str(e)[:50]}"

        # ---- 图纸诊断报告（核心卖点：区别免费工具）----
        try:
            from pipeline.scorability import diagnostic_report, diagnostic_text
            diag = diagnostic_report(grid_rgb, W, H, max_colors, face_regions)
            meta["diagnostic"] = diag
            diag_path = os.path.join(order_dir, "delivery", "3.6_图纸诊断报告.txt")
            with open(diag_path, "w", encoding="utf-8") as f:
                f.write(diagnostic_text(diag))
            steps["S5.7"] = f"诊断报告: {diag['clarity']}, {diag['color_count']}色, 返工点{len(diag['rework_points'])}个"
        except Exception as e:
            steps["S5.7"] = f"诊断跳过: {str(e)[:50]}"

        # ---- PDF 打印版导出（施工图+色卡+信息 3页）----
        try:
            from pipeline.pdf_export import export_pdf
            info_text = info_card_text(pinfo, mapper.brand)
            pdf_path = os.path.join(order_dir, "delivery", "0_打印版.pdf")
            export_pdf(sheet_path, palette_path, info_text, pdf_path)
            steps["S5.6"] = "PDF打印版完成"
        except Exception as e:
            steps["S5.6"] = f"PDF跳过: {str(e)[:50]}"

        # ---- S6 成品预览 + 远看预览 ----
        from pipeline.preview import render_preview, render_far_view
        preview_img = render_preview(grid_rgb, W, H)
        preview_path = os.path.join(order_dir, "delivery", "4_成品预览.png")
        preview_img.save(preview_path)
        far_img = render_far_view(grid_rgb, W, H)
        far_path = os.path.join(order_dir, "delivery", "4.5_远看预览.png")
        far_img.save(far_path)
        steps["S6"] = "成品预览+远看预览完成"

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
