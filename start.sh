#!/bin/bash
# 拼豆工坊一键启动（带 codex/GPT 完整权限，确保 Web 生成可用）
# 用法: ./start.sh  或  bash start.sh

cd "$(dirname "$0")"

echo "🚀 启动拼豆工坊..."
echo "  端口: http://127.0.0.1:8741"
echo "  后端: GPT Image 2 (codex) + 代码施工图管线"
echo ""

# 清理旧进程
pkill -f "uvicorn app.main" 2>/dev/null
sleep 1

# 启动服务器（后台）
nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8741 > server.log 2>&1 &

sleep 3

# 检查
if curl -s -o /dev/null http://127.0.0.1:8741/; then
  echo "✅ 服务器已启动: http://127.0.0.1:8741"
  echo "   浏览器打开即可生图"
else
  echo "❌ 启动失败，查看 server.log"
  tail -10 server.log
fi
