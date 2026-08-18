# -*- coding: utf-8 -*-
"""S1 AI 像素化 + 风格化：调 bl CLI 生成像素底图
提示词 = 通用骨架(像素化/施工要求) + 风格片段 + 规格参数
注意：此步只生成"像素艺术底图"，坐标/色号/清单由代码后处理（图像模型画不准文字）
"""
import subprocess
import os
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

GENERIC_FRAGMENT = (
    "像素拼豆艺术风格。将图片主体转为硬边像素拼豆图案：每个像素块必须是单一纯色、"
    "边界锐利分明，严禁任何渐变、晕染、柔边、半透明、照片质感、混色像素；"
    "色块之间要有清晰分界线，像马赛克瓷砖；"
    "保留脸部、眼睛、嘴巴等关键细节，主体居中，四周保留安全边距，"
    "正面正视，正交俯视图，不要透视。"
)

def build_prompt(style_id="classic", width=30, max_colors=16, extra_subject=""):
    style = config.STYLES.get(style_id, config.STYLES["classic"])
    return (
        f"{GENERIC_FRAGMENT} "
        f"风格: {style['prompt_fragment']}。"
        f"网格约 {width} 格宽，最多 {max_colors} 种颜色。"
        f"{extra_subject}"
    )

def pixelate(source_path, out_path, style_id="classic", width=30, max_colors=16,
             extra_subject="", model=None, out_dir=None, watermark=False):
    """调 bl image generate/edit 生成像素底图
    source_path 为原图（客户图）时用 edit 保持主体；无原图时用 generate
    返回 (success, out_path_or_err)
    """
    prompt = build_prompt(style_id, width, max_colors, extra_subject)
    # 输出目录强制指定到订单 intermediate（沙箱内），避免 bl 默认写 ~/bailian-output
    safe_dir = out_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "_bl_tmp")
    os.makedirs(safe_dir, exist_ok=True)
    cmd = ["bl", "image", "generate", "--prompt", prompt, "--watermark", "false",
           "--out-dir", safe_dir, "--out-prefix", "pixel_base"]
    if source_path and os.path.exists(source_path):
        # 用 edit：以原图为底转像素风，主体保留更准确
        cmd = ["bl", "image", "edit", "--image", source_path, "--prompt", prompt,
               "--watermark", "false", "--out-dir", safe_dir, "--out-prefix", "pixel_base"]
    if model:
        cmd += ["--model", model]
    cmd.append("--quiet")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            return False, r.stderr.strip() or "bl 调用失败"
        # bl --quiet 输出: 生成图片的保存路径（可能相对路径，如 "_bl_tmp/pixel_base.png"）
        out = r.stdout.strip()
        if not out:
            return False, "bl 无输出"
        # 找到第一行看起来像图片路径的行
        import shutil
        saved_path = None
        for line in out.splitlines():
            line = line.strip().strip('"').strip("'")
            if line.endswith((".png", ".jpg", ".jpeg", ".webp")):
                saved_path = line
                break
        if saved_path:
            # 相对路径基于 cwd 解析
            if not os.path.isabs(saved_path):
                saved_path = os.path.join(os.getcwd(), saved_path)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            shutil.copy(saved_path, out_path)
            return True, out_path
        return False, f"无法解析 bl 输出: {out[:200]}"
    except subprocess.TimeoutExpired:
        return False, "AI 生成超时(180s)"
    except Exception as e:
        return False, str(e)
