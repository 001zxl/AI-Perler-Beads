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

def build_prompt(style_id="classic", width=30, max_colors=16, extra_subject="", is_edit=False):
    style = config.STYLES.get(style_id, config.STYLES["classic"])
    if is_edit:
        # 编辑模式（基于原图）：先卡通化再像素化（照片→插画→拼豆）
        return (
            "先将这张照片转换为简洁的卡通插画风格："
            "简化细节、大色块、清晰轮廓、减少噪点和纹理，"
            "颜色层次分明（减少相近色阶），适合手工制作。"
            "然后再转换为严格的拼豆像素图纸：每个像素格必须是单一纯色，"
            "相邻格用清晰的分界网格线隔开，像马赛克拼豆图纸模板，"
            "绝对不能有渐变、阴影、高光、晕染或任何非纯色效果，"
            "每格颜色完全均匀平坦；"
            f"风格: {style['prompt_fragment']}。"
            f"网格约 {width} 格宽，最多 {max_colors} 种颜色。"
            "保留主体形象和标志色，仅做卡通化+像素化。"
        )
    return (
        f"{GENERIC_FRAGMENT} "
        f"风格: {style['prompt_fragment']}。"
        f"网格约 {width} 格宽，最多 {max_colors} 种颜色。"
        f"{extra_subject}"
    )

# GPT Image 2 脚本路径（codex CLI + ChatGPT 订阅，无需 API key）
GEN_SCRIPT = os.path.expanduser("~/.agents/skills/gpt-image-2/scripts/gen.sh")

def _gpt_pixelate(source_path, out_path, prompt, timeout=300):
    """用 GPT Image 2 (gen.sh) 做 image-to-image 像素化
    返回 (success, out_path_or_err)
    """
    if not os.path.exists(GEN_SCRIPT):
        return False, "GPT Image 2 脚本未找到"
    cmd = ["bash", GEN_SCRIPT, "--prompt", prompt]
    if source_path and os.path.exists(source_path):
        cmd += ["--ref", source_path]
    cmd += ["--out", out_path, "--timeout-sec", str(timeout)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30)
        if r.returncode != 0:
            err = r.stderr.strip()[-300:] if r.stderr else "GPT生成失败"
            return False, f"GPT Image 2: {err}"
        out = r.stdout.strip()
        if out and os.path.exists(out):
            return True, out_path
        return False, f"GPT 输出异常: {out[:100]}"
    except subprocess.TimeoutExpired:
        return False, "GPT 生成超时"
    except Exception as e:
        return False, str(e)

def _bl_pixelate(source_path, out_path, prompt, safe_dir, model=None):
    """旧 bl 后端（fallback，key 失效时不可用）"""
    os.makedirs(safe_dir, exist_ok=True)
    cmd = ["bl", "image", "generate", "--prompt", prompt, "--watermark", "false",
           "--out-dir", safe_dir, "--out-prefix", "pixel_base"]
    if source_path and os.path.exists(source_path):
        cmd = ["bl", "image", "edit", "--image", source_path, "--prompt", prompt,
               "--watermark", "false", "--out-dir", safe_dir, "--out-prefix", "pixel_base"]
    if model:
        cmd += ["--model", model]
    cmd.append("--quiet")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            return False, r.stderr.strip() or "bl 调用失败"
        out = r.stdout.strip()
        if not out:
            return False, "bl 无输出"
        import shutil
        saved_path = None
        for line in out.splitlines():
            line = line.strip().strip('"').strip("'")
            if line.endswith((".png", ".jpg", ".jpeg", ".webp")):
                saved_path = line
                break
        if saved_path:
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

def pixelate(source_path, out_path, style_id="classic", width=30, max_colors=16,
             extra_subject="", model=None, out_dir=None, watermark=False, backend="gpt"):
    """生成像素底图
    backend="gpt": GPT Image 2（image-to-image，ChatGPT 订阅，首选）
    backend="bl": 百炼（需 API key，fallback）
    """
    prompt = build_prompt(style_id, width, max_colors, extra_subject, is_edit=True)
    safe_dir = out_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "_bl_tmp")
    if backend == "gpt":
        return _gpt_pixelate(source_path, out_path, prompt)
    return _bl_pixelate(source_path, out_path, prompt, safe_dir, model)
