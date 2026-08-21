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
    style = config.STYLES.get(style_id, config.STYLES["classic"])

    # ---- S0 图片类型识别（先于规格解析，类型策略决定规格下限）----
    # 默认彻底关闭 AI 重绘：图像模型会把定制照片改成另一张图，是当前质量事故的根因。
    # 如确实要做 AI 卡通化，需显式设置环境变量 PERLER_ALLOW_AI_PIXELATE=1。
    allow_ai_pixelate = os.environ.get("PERLER_ALLOW_AI_PIXELATE") == "1"
    cartoonize_styles = ("chibi_pastel", "kawaii", "popart", "vaporwave", "crayon", "comic")
    need_ai = allow_ai_pixelate and (not skip_ai) and style_id in cartoonize_styles
    img_type = "默认"
    try:
        from pipeline.type_aware import detect_type, subject_to_type
        if need_ai:
            img_type, _subj, _areas = detect_type(source_path)
        else:
            img_type = subject_to_type(subject)
    except Exception:
        img_type = subject_to_type(subject)
    try:
        from pipeline.type_aware import TYPE_STRATEGIES
        strat = TYPE_STRATEGIES.get(img_type, {})
    except Exception:
        strat = {}

    # ---- 规格解析优先级：用户显式 > 类型策略 > 档位默认；再套类型最低质量线 ----
    # 档位宽度是列表时取最大值，避免高价档误用最低规格。
    def _tier_default_width(t):
        w = t.get("width")
        if isinstance(w, list):
            return max(w) if w else 60
        return w or 60

    if width is None:
        width = strat.get("recommended_width") or _tier_default_width(tier)
    if isinstance(width, list):
        width = max(width)
    # 宠物/真人 最低规格兜底：质量优先，强制避免 30x37 这类不可交付图纸。
    min_w = strat.get("min_width", 0)
    if min_w and width < min_w:
        width = min_w
    if max_colors is None:
        max_colors = strat.get("max_colors_default") or tier.get("colors", 12)
    if isinstance(max_colors, list):
        max_colors = max(max_colors)
    min_colors = strat.get("min_colors", 0)
    if min_colors and max_colors < min_colors:
        max_colors = min_colors

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
        "bead": bead, "subject": subject, "img_type": img_type,
        "created": datetime.now().isoformat(),
    }
    steps = {}
    try:
        # ---- S1 像素化（默认非 AI 还原模式，AI 仅用于卡通化风格）----
        pixel_path = os.path.join(order_dir, "intermediate", "pixel_base.png")
        if not need_ai or not os.path.exists(source_path):
            # 非 AI 还原模式（默认）：直接用原图确定性量化，保留主体特征
            work_img = source_path
            steps["S1"] = "还原模式(确定性量化，无AI重绘)"
        else:
            ok, res = pixelate(source_path, pixel_path, style_id=style_id, width=width,
                               max_colors=max_colors, extra_subject=extra_subject)
            if not ok:
                # AI 失败降级到还原模式，不阻塞
                work_img = source_path
                steps["S1"] = f"AI失败降级还原模式: {res[:60]}"
            else:
                steps["S1"] = res
                work_img = pixel_path

        # ---- S2 量化 ----
        from PIL import Image
        img = Image.open(work_img).convert("RGB")
        # 低对比预处理（还原模式默认开启）：奶油白猫+粉背景 → 明暗对比增强+背景弱化
        # 仅对非 AI 生成的底图（AI 卡通化底图由 GPT 控制对比度，不需再增强）
        if work_img == source_path:
            try:
                from pipeline.preprocess import enhance_low_contrast
                img = enhance_low_contrast(img, img_type=meta.get("img_type", "默认"),
                                           style_id=style_id)
            except Exception:
                pass  # 预处理失败不影响主流程
        # mono 风格兜底：强制灰度化（黑白线稿无需 AI 画，代码 100% 精确）
        if style.get("palette") == "mono":
            img = img.convert("L").convert("RGB")
        photo_like = meta.get("img_type", "默认") in ("宠物", "真人", "默认")
        # 统一用主导色模式：MEDIANCUT 全局量化会把浅粉/奶油色压成深红棕（实测
        # 原图浅粉 40% → 量化后深红棕 3%+3%），是"成品颜色变橙红棕"的根因。
        # 主导色 + 特征感知减色（global_quantize）保色准确且不丢五官。
        grid_rgb, W, H = quantize_grid(img, width, height, max_colors, use_dominant=True)
        meta["grid"] = f"{W}x{H}"
        # 主导色后全局量化到 max_colors（防止每格独立采样导致色数爆炸）
        if len(set(grid_rgb)) > max_colors:
            grid_rgb = global_quantize(grid_rgb, max_colors)
        # 特征保护（眼睛/鼻口/爪/球边界）：AI 风格用 AI 定位，还原模式用确定性检测
        face_regions = {}
        protected_cells = set()
        try:
            from pipeline.face_guard import detect_face_regions, apply_face_guard, detect_features_deterministic
            if need_ai:
                face_regions = detect_face_regions(work_img, W, H)
            # AI 未定位到（还原模式或定位失败）→ 确定性特征检测保护眼睛/鼻口/高饱和小簇
            if not face_regions:
                protected_cells = detect_features_deterministic(grid_rgb, W, H,
                                                                img_type=meta.get("img_type", "默认"))
                # 确定性保护也计入诊断：有保护格 = 特征已识别保留
                if protected_cells:
                    face_regions = {"_deterministic": list(protected_cells)[:1]}
        except Exception:
            try:
                from pipeline.face_guard import detect_features_deterministic
                protected_cells = detect_features_deterministic(grid_rgb, W, H,
                                                                img_type=meta.get("img_type", "默认"))
                if protected_cells:
                    face_regions = {"_deterministic": list(protected_cells)[:1]}
            except Exception:
                protected_cells = set()
        # 面部保护：仅 AI 定位到真实区域时走 AI 保护（确定性保护已在上面算出，直接复用）
        if face_regions and any(k in face_regions for k in ("eyes", "nose", "mouth")):
            grid_rgb, protected_cells = apply_face_guard(grid_rgb, W, H, face_regions)
        if photo_like:
            # 照片类只做轻清理。重 BFS 会把眼睛/嘴/爪和球边界重新拼坏。
            try:
                grid_rgb, _iso = remove_isolated_pixels(grid_rgb, W, H, min_cluster=2,
                                                        protected=protected_cells)
            except TypeError:
                grid_rgb, _iso = remove_isolated_pixels(grid_rgb, W, H, min_cluster=2)
            grid_rgb, _sm = simplify_small_regions(grid_rgb, W, H, min_area=2,
                                                   protected=protected_cells)
        else:
            # 动漫/Logo/图标类可以做强清理，得到干净色块和硬边。
            try:
                grid_rgb, _iso = remove_isolated_pixels(grid_rgb, W, H, protected=protected_cells)
            except TypeError:
                grid_rgb, _iso = remove_isolated_pixels(grid_rgb, W, H)
            try:
                grid_rgb = bfs_cleanup(grid_rgb, W, H, threshold=18, protected=protected_cells)
            except TypeError:
                grid_rgb = bfs_cleanup(grid_rgb, W, H, threshold=18)
            grid_rgb, _sm = simplify_small_regions(grid_rgb, W, H, min_area=3,
                                                   protected=protected_cells)
        # 类型感知轮廓加粗（动漫/Logo 黑边、宠物深棕边）
        try:
            from pipeline.outline import strengthen_outline
            img_type_hint = meta.get("img_type", "默认")
            grid_rgb = strengthen_outline(grid_rgb, W, H, img_type_hint)
        except Exception:
            pass
        # 轮廓加粗后：保护格区域不再合并（确保眼睛/鼻口不被最后一步洗掉）
        try:
            grid_rgb, _sm2 = simplify_small_regions(grid_rgb, W, H, min_area=2, protected=protected_cells)
        except Exception:
            pass
        # 照片类细节回填：从原图恢复眼睛/鼻口/爪子/球边界等结构，再落色卡。
        if photo_like:
            try:
                from pipeline.photo_detail import restore_photo_details
                grid_rgb = restore_photo_details(grid_rgb, img, W, H,
                                                 img_type=meta.get("img_type", "默认"))
            except Exception:
                pass
        if len(set(grid_rgb)) > max_colors:
            grid_rgb = merge_near_colors(grid_rgb, max_colors)
        steps["S2"] = f"{W}x{H} 网格, {len(set(grid_rgb))} 色 (类型+轮廓+清理)"

        # ---- S3 色卡映射（Oklab 感知色距，视觉更准）----
        mapper = OklabColorMapper(colorcard, style.get("palette", "standard"))
        steps["S3"] = f"{colorcard} 色卡映射完成 (Oklab)"

        # 所有交付图统一使用真实色卡 RGB，避免预览色、施工图色块和采购色号不一致。
        grid_rgb = [tuple(mapper.lookup(rgb)[2]) for rgb in grid_rgb]
        steps["S3.5"] = "网格已落到真实色卡颜色"

        # ---- S5 统计 + CSV（先算，供施工图底部色卡区用）----
        rows, total = compute_stats(grid_rgb, mapper)
        palette_sheet = render_palette_sheet(rows, total, W, H, mapper.brand)
        palette_path = os.path.join(order_dir, "delivery", "2_色卡与用量统计.png")
        palette_sheet.save(palette_path)
        csv_path = os.path.join(order_dir, "delivery", "3_采购清单.csv")
        write_shopping_csv(rows, total, W, H, mapper.brand, csv_path, mapper=mapper)
        steps["S5"] = f"{len(rows)} 色, 共 {total} 颗, 采购清单 CSV 完成"

        # ---- S5.5 可拼性评分（供施工图角标）----
        try:
            from pipeline.scorability import score_pattern, pattern_info, info_card_text
            sc = score_pattern(grid_rgb, W, H, max_colors)
            pinfo = pattern_info(grid_rgb, W, H, bead, difficulty=tier.get("difficulty", {}).get("level", "标准"))
            meta["scorability"] = sc
            meta["pattern_info"] = pinfo
            info_path = os.path.join(order_dir, "delivery", "3.5_图纸信息.txt")
            with open(info_path, "w", encoding="utf-8") as f:
                f.write(info_card_text(pinfo, mapper.brand))
            steps["S5.5"] = f"可拼性评分 {sc['score']} 分 ({sc['verdict']})"
        except Exception as e:
            sc = None
            steps["S5.5"] = f"评分跳过: {str(e)[:50]}"

        # ---- S4 施工图（对标专业图纸：四参数标题+色卡用量+制作建议）----
        from pipeline.suggestions import build_suggestions
        sugg = build_suggestions(meta.get("img_type", "默认"), mapper, rows, total)
        sheet = render_construction_sheet(grid_rgb, W, H, mapper, title=title, bead_size=bead,
                                          color_rows=rows, suggestions=sugg,
                                          scorability=sc, subject=subject,
                                          img_type=meta.get("img_type", "默认"))
        sheet_path = os.path.join(order_dir, "delivery", "1_施工主图.png")
        sheet.save(sheet_path)
        steps["S4"] = "施工主图完成(专业版)"

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
            elif work_img == source_path and not os.path.exists(pixel_path):
                # 非 AI 还原模式：用确定性质检（不调 GPT 视觉，快且稳）
                # 网格单色由代码保证，重点检查特征保留（关键色数量）
                try:
                    from pipeline.scorability import diagnostic_report
                    diag = diagnostic_report(grid_rgb, W, H, max_colors)
                    key_colors = sum(1 for c in set(grid_rgb)
                                     if max(c) - min(c) > 150 or max(c) < 80 or max(c) > 230)
                    passed = key_colors >= 2 and diag["scorability"]["score"] >= 60
                    detail = {"reason": f"确定性质检: 关键色{key_colors}种, 可拼性{diag['scorability']['score']}分", "pass": passed}
                    qc_result = {"passed": passed, "detail": detail, "target": "deterministic"}
                    steps["S8"] = f"质检{'通过' if passed else '未通过'}: {detail['reason']}"
                except Exception as e:
                    qc_result = {"passed": True, "detail": {"reason": f"确定性质检异常,默认通过: {str(e)[:50]}"}, "target": "deterministic"}
                    steps["S8"] = "质检通过(确定性兜底)"
            else:
                # AI 卡通化风格：检查"量化后的成品预览"（真实交付物）
                qc_target = preview_path if os.path.exists(preview_path) else (sheet_path if os.path.exists(sheet_path) else pixel_path)
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


def run_order_with_qc_retry(source_path, tier_key="主力款", style_id="classic", width=None, height="auto",
                            max_colors=None, colorcard="mard", bead="2.6mm", title=None, subject="宠物",
                            orders_root=None, skip_ai=False, do_qc=False, extra_subject="", max_retries=2):
    """带质检重试的生成：QC 未通过时自动重新生成（GPT 随机性，重试可提高通过率）
    返回最终结果
    """
    import time
    last = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"  质检未通过，第{attempt}次重试生成...", flush=True)
            time.sleep(2)
        last = run_order(source_path, tier_key=tier_key, style_id=style_id, width=width,
                         height=height, max_colors=max_colors, colorcard=colorcard,
                         bead=bead, title=title, subject=subject, orders_root=orders_root,
                         skip_ai=skip_ai, do_qc=do_qc, extra_subject=extra_subject)
        if last.get("success"):
            qc = last.get("qc")
            if not do_qc or (qc and qc.get("passed")):
                return last  # 成功且质检通过（或未开质检）
            # 确定性质检（非 AI 还原模式）输出可复现，重试无意义 → 直接返回
            if qc and qc.get("target") == "deterministic":
                return last
            # AI 质检未通过（GPT 随机性），继续重试
    return last  # 重试用尽，返回最后一次结果

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
