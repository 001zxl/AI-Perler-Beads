#!/bin/bash
# 检查 GPT Image 2 链路是否就绪（ChatGPT App + codex）
echo "🔍 检查 GPT Image 2 链路..."
echo ""

# 1. 检查 ChatGPT App
APP_COUNT=$(ps aux | grep "ChatGPT.app" | grep -v grep | wc -l | tr -d ' ')
if [ "$APP_COUNT" -gt 0 ]; then
  echo "✅ ChatGPT App: 运行中"
else
  echo "❌ ChatGPT App: 未运行（请手动打开 ChatGPT 应用并保持登录）"
  echo "   尝试启动: open -a ChatGPT"
  open -a ChatGPT 2>/dev/null
  sleep 5
fi

# 2. 清理 codex 旧会话（防卡死）
find ~/.codex/sessions -name "*.jsonl" -mmin +10 -delete 2>/dev/null
echo "🧹 codex 会话已清理"

# 3. 测试 codex
echo "⏳ 测试 codex 连接..."
if echo "pong" | timeout 40 codex exec --skip-git-repo-check --sandbox read-only --color never 2>/dev/null | grep -q pong; then
  echo "✅ codex: 连接正常，GPT Image 2 可用"
else
  echo "❌ codex: 无响应（ChatGPT App 未就绪？）"
fi
