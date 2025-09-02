#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

# Load environment variables from backend .env file
if [ -f "$SCRIPT_DIR/backend/.env" ]; then
  export $(cat "$SCRIPT_DIR/backend/.env" | sed 's/#.*//g' | xargs)
fi

# Load environment variables from frontend .env file
if [ -f "$SCRIPT_DIR/frontend/.env" ]; then
  export $(cat "$SCRIPT_DIR/frontend/.env" | sed 's/#.*//g' | xargs)
fi

# Use environment variables or default values
FRONTEND_PORT=${REACT_APP_FRONTEND_PORT:-3001}
BACKEND_PORT=${BACKEND_PORT:-5001}

# 清理前端和后端可能占用的端口
echo "正在清理端口 $FRONTEND_PORT 和 $BACKEND_PORT..."
kill -9 $(lsof -t -i:$FRONTEND_PORT) 2>/dev/null || echo "端口$FRONTEND_PORT上没有找到进程"
kill -9 $(lsof -t -i:$BACKEND_PORT) 2>/dev/null || echo "端口$BACKEND_PORT上没有找到进程"

# 启动后端服务
echo "正在启动后端服务..."
cd "$SCRIPT_DIR/backend"
python3 app.py &
BACKEND_PID=$!
cd "$SCRIPT_DIR"

# 启动前端开发服务器
echo "正在启动前端开发服务器..."
cd "$SCRIPT_DIR/frontend"
npm start &
FRONTEND_PID=$!

# 等待进程结束
wait $BACKEND_PID
wait $FRONTEND_PID