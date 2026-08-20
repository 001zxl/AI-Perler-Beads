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
        # 编辑模式（基于原图）：忠实保留源图主体，仅做像素化，禁止艺术化改动
        return (
            "严格参照这张照片，只做像素化处理，不要改变任何内容："
            "完整保留主体的形状、五官比例（眼睛大小形状、鼻子位置、嘴巴、耳朵轮廓）、"
            "表情和姿态，不要放大或缩小任何部位，不要卡通化、不要重新设计。"
            "特别注意：保留眼睛的形状和瞳孔高光（不要变成方块或圆点）、"
            "保留粉色鼻子的小三角形状、保留嘴巴曲线，这些是识别主体的关键。"
            "转换方式：把照片变成马赛克像素网格图，每个格子用该位置照片的平均色填充，"
            "格子是单一纯色，格与格之间干净分界，无渐变/阴影/高光/晕染，"
            "像低分辨率的照片马赛克，而不是插画或漫画。"
            f"网格约 {width} 格宽，最多 {max_colors} 种颜色，"
            "必须保留原图能识别的主体特征。"
        )
    return (
        f"{GENERIC_FRAGMENT} "
        f"风格: {style['prompt_fragment']}。"
        f"网格约 {width} 格宽，最多 {max_colors} 种颜色。"
        f"{extra_subject}"
    )

# GPT Image 2 脚本路径（codex CLI + ChatGPT 订阅，无需 API key）
GEN_SCRIPT = os.path.expanduser("~/.agents/skills/gpt-image-2/scripts/gen.sh")

def _clean_codex_sessions(max_age_min=10, max_size_mb=200):
    """清理 codex 旧会话，防止累积卡死（每次生成前调用）"""
    import glob
    sessions_dir = os.path.expanduser("~/.codex/sessions")
    try:
        files = glob.glob(os.path.join(sessions_dir, "**", "*.jsonl"), recursive=True)
        import time
        now = time.time()
        for f in files:
            try:
                if now - os.path.getmtime(f) > max_age_min * 60:
                    os.remove(f)
            except Exception:
                pass
    except Exception:
        pass

def _gpt_pixelate(source_path, out_path, prompt, timeout=300, retries=3):
    """用 GPT Image 2 (gen.sh) 做 image-to-image 像素化
    带自动重试（codex app-server 初始化不稳定，重试可提高成功率）
    返回 (success, out_path_or_err)
    """
    import time
    _clean_codex_sessions()  # 预防会话累积卡死
    if not os.path.exists(GEN_SCRIPT):
        return False, "GPT Image 2 脚本未找到"
    cmd = ["bash", GEN_SCRIPT, "--prompt", prompt]
    if source_path and os.path.exists(source_path):
        cmd += ["--ref", source_path]
    cmd += ["--out", out_path, "--timeout-sec", str(timeout)]
    last_err = ""
    for attempt in range(retries):
        if attempt > 0:
            time.sleep(3)  # 重试前短暂等待，让 codex 服务恢复
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30)
            if r.returncode != 0:
                last_err = r.stderr.strip()[-200:] if r.stderr else "GPT生成失败"
                continue  # 重试
            out = r.stdout.strip()
            if out and os.path.exists(out):
                return True, out_path
            last_err = f"GPT 输出异常: {out[:100]}"
        except subprocess.TimeoutExpired:
            last_err = "GPT 生成超时"
        except Exception as e:
            last_err = str(e)
    return False, f"GPT Image 2 (重试{retries}次后): {last_err}"

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
