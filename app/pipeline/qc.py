# -*- coding: utf-8 -*-
"""S8 AI 质检：视觉模型检查 AI 像素底图（像素化/单色/细节/风格）
用 codex CLI（ChatGPT 订阅）替代失效的 bl vision
"""
import subprocess
import json

QC_PROMPT = (
    "这是一张拼豆成品的预览图（已经量化处理，每格应该是单一纯色）。"
    "请严格检查以下四项，逐项回答 通过/不通过 并给出理由，最后一行输出 JSON: "
    '{"pixel_ok": true/false, "mono_ok": true/false, "detail_ok": true/false, "style_ok": true/false, "pass": true/false, "reason": "简述"}。'
    "检查项: 1)pixel_ok 是否呈现出拼豆/马赛克风格（由方块颗粒组成，而非平滑照片）; "
    "2)mono_ok 每个颗粒是否为单一纯色、无明显渐变晕染（量化后应为纯色）; "
    "3)detail_ok 主体（脸/五官等关键细节）是否完整可辨、能认出原主体; "
    "4)style_ok 整体是否符合拼豆图纸的清晰风格。"
    "注意：这是成品预览图，可能带有圆润颗粒效果或轻微光影模拟，属于正常呈现，不作为不合格依据。"
)

def _codex_vision(image_path, prompt, timeout=150):
    """用 codex CLI 看图（ChatGPT 订阅，替代 bl vision）
    返回 (ok, content_or_err)
    """
    cmd = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only",
           "--color", "never", "-i", image_path]
    try:
        r = subprocess.run(cmd, input=prompt + "\n", capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return False, (r.stderr.strip()[-300:] or "codex 视觉失败")
        out = r.stdout.strip()
        if not out:
            return False, "codex 无输出"
        return True, out
    except subprocess.TimeoutExpired:
        return False, "质检超时"
    except Exception as e:
        return False, str(e)

def qc_image(image_path, style_desc="", model=None):
    """质检 AI 像素底图：像素化/单色/细节/风格
    用 codex vision（GPT 后端）替代 bl vision
    返回 (pass, detail_dict)
    """
    prompt = QC_PROMPT
    if style_desc:
        prompt = f"风格要求: {style_desc}。" + prompt
    ok, content = _codex_vision(image_path, prompt)
    if not ok:
        return False, {"error": content, "raw": ""}
    # 从 codex 输出提取 JSON
    import re
    m = None
    for cand in re.findall(r"\{[^{}]*\}", content, re.S):
        if '"pass"' in cand:
            m = cand
    if m is None:
        cands = re.findall(r"\{[^{}]*\}", content, re.S)
        m = cands[-1] if cands else None
    if m:
        try:
            data = json.loads(m)
            if "pass" in data:
                return bool(data.get("pass")), data
        except Exception:
            pass
    # 文本关键词兜底判断
    if "通过" in content or "pass" in content.lower():
        return True, {"pass": True, "raw": content[:300], "note": "文本判断"}
    if "不通过" in content or "未通过" in content or "fail" in content.lower():
        return False, {"pass": False, "raw": content[:300], "note": "文本判断"}
    return False, {"raw": content[:300], "error": "未解析出质检结果"}
