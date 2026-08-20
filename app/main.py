# -*- coding: utf-8 -*-
"""拼豆工坊 Web 后端：上传图 + 选档/风格/规格 → 生成 → 下载交付包"""
import sys
import os
import json
import shutil
import threading
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from pipeline.run import run_order, run_order_with_qc_retry
from pipeline.deliver import make_order_dir
import feedback as feedback_mod

from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="拼豆工坊")

# ---------- 内置定时任务（替代 crontab，随服务器启动）----------
import threading

SCHEDULE_HOURS = [9, 14, 21]  # 每天 9/14/21 点自动跑

def _scheduler_loop():
    import time as _time
    while True:
        try:
            now = _time.localtime()
            if now.tm_hour in SCHEDULE_HOURS and now.tm_min == 0:
                print(f"[scheduler] {_time.strftime('%Y-%m-%d %H:%M')} 开始每日热点任务", flush=True)
                try:
                    import subprocess, sys as _sys
                    base = os.path.dirname(os.path.abspath(__file__))
                    r = subprocess.run([_sys.executable, "-m", "app.run_daily", "--limit", "3"],
                                       cwd=os.path.dirname(base), capture_output=True, text=True, timeout=1800)
                    print(f"[scheduler] 完成: {r.stdout[-300:]} {r.stderr[-200:]}", flush=True)
                except Exception as e:
                    print(f"[scheduler] 任务异常: {e}", flush=True)
                _time.sleep(120)  # 防止同一分钟内重复触发
        except Exception as e:
            print(f"[scheduler] loop err: {e}", flush=True)
        _time.sleep(30)

_threading = threading.Thread(target=_scheduler_loop, daemon=True)
_threading.start()

ORDERS_ROOT = config.ORDERS_DIR
os.makedirs(ORDERS_ROOT, exist_ok=True)

# 简单的内存任务表（单机够用）
TASKS = {}

# ---------- 静态资源 ----------
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))

# ---------- 配置接口 ----------
@app.get("/api/meta")
def get_meta():
    return {
        "tiers": config.TIERS,
        "styles": config.STYLES,
        "style_health": feedback_mod.style_health(),
        "colorcards": {k: {"brand": v["brand"], "bead_size_mm": v.get("bead_size_mm"), "note": v.get("note",""), "color_count": len(v["colors"])} for k, v in config.COLORCARDS.items()},
    }

# ---------- 生成任务 ----------
class GenerateReq(BaseModel):
    tier: str = "主力款"
    style: str = "classic"
    width: Optional[int] = None
    colors: Optional[int] = None
    colorcard: str = "mard"
    bead: str = "2.6mm"
    subject: str = "宠物"
    title: Optional[str] = None
    do_qc: bool = True
    skip_ai: bool = False

@app.post("/api/generate")
async def generate(file: UploadFile = File(...), tier: str = Form("主力款"),
                   style: str = Form("classic"), width: Optional[int] = Form(None),
                   colors: Optional[int] = Form(None), colorcard: str = Form("mard"),
                   bead: str = Form("2.6mm"), subject: str = Form("宠物"),
                   title: Optional[str] = Form(None), do_qc: bool = Form(True),
                   skip_ai: bool = Form(False)):
    """同步生成（单图，耗时约 30s-3min）"""
    # 保存上传图
    task_id = datetime.now().strftime("web_%Y%m%d_%H%M%S")
    order_dir = make_order_dir(ORDERS_ROOT, task_id)
    src_path = os.path.join(order_dir, "source", "upload" + os.path.splitext(file.filename or "x.jpg")[1])
    with open(src_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    res = run_order_with_qc_retry(src_path, tier_key=tier, style_id=style, width=width,
                    max_colors=colors, colorcard=colorcard, bead=bead,
                    subject=subject, title=title, do_qc=do_qc, skip_ai=skip_ai)
    TASKS[task_id] = res
    if not res["success"]:
        return JSONResponse(status_code=500, content=res)
    return res

@app.get("/api/tasks")
def list_tasks():
    return {"tasks": [{k: (v if k != "steps" else list(v.keys())) for k, v in t.items() if k in ("order_id", "grid", "colors", "total", "success", "zip", "files")} for t in TASKS.values()][-20:]}

@app.get("/api/orders/{order_id}/delivery/{fname}")
def get_delivery_file(order_id: str, fname: str):
    """下载交付文件（限 delivery 目录）"""
    safe = os.path.basename(fname)
    path = os.path.join(ORDERS_ROOT, order_id, "delivery", safe)
    if not os.path.exists(path):
        raise HTTPException(404, "文件不存在")
    return FileResponse(path, filename=safe)

@app.get("/api/orders/{order_id}/zip")
def get_zip(order_id: str):
    path = os.path.join(ORDERS_ROOT, order_id, "archive", f"{order_id}_交付包.zip")
    if not os.path.exists(path):
        raise HTTPException(404, "交付包不存在")
    return FileResponse(path, filename=f"{order_id}_交付包.zip")

# ---------- 三轨计费接口（按单/按次包/会员）----------
@app.get("/api/credits/packages")
def get_packages():
    import credit_system
    return {"packages": credit_system.PACKAGES}

@app.get("/api/credits/check")
def check_credits(name: str = ""):
    import credit_system
    if not name:
        return {"success": False, "error": "请输入客户名"}
    return {"success": True, **credit_system.check(name)}

@app.post("/api/credits/purchase")
async def purchase_credits(name: str = Form(...), package: str = Form(...),
                           amount: Optional[float] = Form(None)):
    """购买套餐（线下收款后手动充值入账）"""
    import credit_system
    res = credit_system.purchase(name, package, pay_amount=amount)
    return res

@app.post("/api/credits/consume")
async def consume_credits(name: str = Form(...), order_id: str = Form("")):
    """出图扣次（会员期内免费）"""
    import credit_system
    return credit_system.consume(name)

@app.get("/api/credits/all")
def list_credits():
    import credit_system
    return credit_system.list_all()

# ---------- 热点雷达接口 ----------
@app.get("/api/hotspots")
def get_hotspots():
    """当前热点列表（含 AI 过滤结果）"""
    import hotspot
    data = hotspot.load_hotspots()
    return data

@app.post("/api/hotspots/add")
async def add_hotspot(word: str = Form(...), character: str = Form(""),
                       category: str = Form("其他"), source: str = Form("手动")):
    """手动添加热点（小红书等受限源的人工补充入口）"""
    import hotspot
    data = hotspot.load_hotspots()
    items = data.get("items", [])
    items.insert(0, {"word": word, "character": character or word, "category": category,
                     "source": source, "heat": 0, "reason": "手动添加", "url": ""})
    hotspot.save_hotspots(items)
    return {"success": True, "count": len(items)}

@app.post("/api/hotspots/refresh")
def refresh_hotspots():
    """手动刷新热点（抓取+AI过滤+存库）"""
    import hotspot
    items = hotspot.collect_hotspots(use_ai_filter=True)
    return {"success": True, "count": len(items), "items": items}

@app.post("/api/xianyu/export")
async def xianyu_export(keyword: str = Form(""), character: str = Form("")):
    """导出闲鱼发布物料（标题/描述/商品图/命令）"""
    import xianyu_publish
    import hot_batch
    gallery = hot_batch.load_gallery()
    target = None
    for e in gallery.get("items", []):
        if (character and e.get("character") == character) or (keyword and e.get("keyword") == keyword):
            target = e; break
    if not target:
        return {"success": False, "error": "画廊中未找到该热点，先生成图纸"}
    res = xianyu_publish.export_post(target)
    return {"success": True, **res}

@app.get("/api/hotgallery")
def get_hotgallery():
    """热点图纸画廊"""
    import hot_batch
    return hot_batch.load_gallery()

@app.post("/api/hotgallery/generate")
async def hot_generate(keyword: str = Form(...), character: str = Form(""),
                       styles: str = Form("classic,chibi_pastel"), do_qc: bool = Form(True)):
    """为热点角色生成图纸（一键生成同款）"""
    import hot_batch
    item = {"word": keyword, "character": character or keyword, "heat": 0, "source": "Web"}
    res = hot_batch.process_hotspot(item, styles=tuple(s.strip() for s in styles.split(",")))
    if res.get("success"):
        return {"success": True, "entry": res["entry"]}
    return {"success": False, "error": res.get("error", "生成失败")}

# ---------- 反馈学习接口 ----------
@app.get("/api/feedback")
def list_feedback():
    """经验库列表"""
    return {"feedbacks": feedback_mod.list_feedbacks(), "stats": feedback_mod.stats()}

@app.post("/api/feedback")
async def add_feedback(order_id: str = Form(...), satisfied: str = Form("true"),
                       reason: str = Form(""), detail: str = Form(""),
                       action: str = Form(""), lesson: str = Form("")):
    """记录客户反馈（满意/不满意+原因+调整动作+经验）"""
    fb = feedback_mod.add_feedback(order_id, satisfied == "true", reason, detail, action, lesson)
    return {"success": True, "feedback": fb}

@app.get("/api/lessons/{style}")
def lessons_for_style(style: str):
    """某风格的历史经验建议（生成时可展示给操作者）"""
    hits = feedback_mod.get_lessons_for(style=style)
    return {"hits": len(hits), "summary": feedback_mod.summarize_lessons(hits)}

# ---------- 人工微调接口 ----------
@app.post("/api/tune")
async def tune_pattern(order_id: str = Form(...), action: str = Form("reduce_colors"),
                       colors: Optional[int] = Form(None)):
    """人工微调：基于源图重新生成（减色/去杂点/加轮廓）
    action: reduce_colors(减色) / denoise(去杂点) / stronger_outline(加轮廓)
    """
    meta_path = os.path.join(ORDERS_ROOT, order_id, "meta.json")
    if not os.path.exists(meta_path):
        return {"success": False, "error": "订单不存在"}
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    src_dir = os.path.join(ORDERS_ROOT, order_id, "source")
    src_files = os.listdir(src_dir) if os.path.exists(src_dir) else []
    if not src_files:
        return {"success": False, "error": "无源图"}
    src_path = os.path.join(src_dir, src_files[0])
    kwargs = {"tier_key": meta.get("tier", "主力款"), "style_id": meta.get("style", "classic")}
    if action == "reduce_colors":
        kwargs["max_colors"] = colors or 8
    res = run_order(src_path, **kwargs)
    return {"success": True, **res}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8741)
