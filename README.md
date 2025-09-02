# 知识库 AI 增强工具

本项目是一个基于飞书知识库的 AI 增强工具，旨在通过大语言模型（LLM）提升知识管理和利用的效率。它能够对新文档进行智能分析，提出归档建议，并对知识库中的现有内容进行 AI 评估和优化。

## 📋 更新日志

### 2025-09-02 更新
- **端口配置优化**：前端端口为3001，后端端口为5001，提高端口配置的一致性和可维护性。
- **依赖更新**：更新了前后端依赖包，确保系统稳定性和安全性。
- **部署流程优化**：简化了部署流程，提供更清晰的部署指南。

## ✨ 功能特性

- **飞书授权登录**：通过飞书 OAuth 2.0 实现安全的用户身份认证。
- **知识空间浏览**：支持分页浏览用户授权范围内的所有知识空间。
- **知识库节点树**：递归获取并展示知识库的完整层级结构。
- **文档导入 AI 分析**：
    - 支持 `docx`、`doc`、`wiki` 多种飞书文档链接导入。
    - 提取文档内容，结合知识库现有结构，由 LLM 给出专业评估：
        - **内容匹配度分析**：评估导入文档与知识库的相关性。
        - **归属节点建议**：推荐最适合的 1-3 个存放位置。
        - **导入决策**：给出“建议导入”或“暂不建议导入”的最终决策。
- **当前文档 AI 评估**：
    - 对知识库中的现有文档进行 AI 分析。
    - 支持自定义 Prompt 模板，灵活调整评估维度。
- **流式响应**：所有 LLM 的分析和评估结果均以流式（Streaming）方式实时返回，提升用户体验。
- **健壮的日志系统**：
    - **日志轮转**：按大小自动分割日志文件，防止单个文件过大。
    - **自动清理**：限制日志文件总数和备份数量，避免磁盘空间无限增长。
    - **后台监控**：定期检查日志目录大小，并在超过阈值时发出警告。
    - **管理 API**：提供手动触发日志清理和状态查询的接口。
- **前后端分离架构**：采用 React 前端与 Flask 后端，职责清晰，易于维护和扩展。
- **详细的日志记录**：所有关键操作、接口请求和第三方 API 调用均有详细日志，便于问题排查。

## 🏗️ 系统架构

本项目采用经典的前后端分离架构：

- **前端 (Frontend)**：
    - 使用 `React` 构建的用户界面。
    - 负责用户交互、数据展示和 API 请求。
    - 通过 `setupProxy.js` 将 `/api` 请求代理到后端，解决跨域问题。
- **后端 (Backend)**：
    - 使用 `Flask` 搭建的 RESTful API 服务器。
    - 负责业务逻辑处理、与飞书开放平台和 LLM 服务交互。
    - 提供用户认证、知识库数据获取、AI 分析等核心功能。

## 🛠️ 技术栈

- **前端**:
    - [React](https://reactjs.org/)
    - [Ant Design](https://ant.design/)
    - [axios](https://axios-http.com/)
- **后端**:
    - [Flask](https://flask.palletsprojects.com/)
    - [requests](https://requests.readthedocs.io/)
    - [python-dotenv](https://github.com/theskumar/python-dotenv)
    - [OpenAI SDK](https://github.com/openai/openai-python)
- **数据库**: 无，数据实时从飞书 API 获取。
- **LLM**: 支持兼容 OpenAI API 协议的各类大语言模型。

## 🔐 飞书接口权限

为了确保应用所有功能正常运行，您需要在飞书开放平台的应用配置中，为您的应用添加以下权限。应用在请求授权时，会申请以下范围的权限，这些权限需要用户身份授权：

| 权限 (Scope)             | 描述               |
| ------------------------ | ------------------ |
| `docx:document:readonly` | 读取云文档内容     |
| `wiki:node:move`         | 移动知识库节点     |
| `wiki:node:retrieve`     | 获取知识库节点信息 |
| `wiki:space:read`        | 读取知识空间列表   |
| `wiki:space:retrieve`    | 获取知识空间信息   |
| `wiki:node:read`         | 读取知识库节点内容 |
| `wiki:wiki:readonly`     | 读取知识库内容     |

### 权限说明

以上权限均为用户身份授权权限，意味着应用需要获得用户的明确授权才能访问其飞书知识库数据。这些权限允许应用：

1. **读取文档内容**：通过 `docx:document:readonly` 和 `wiki:wiki:readonly` 权限，应用可以读取用户授权范围内的文档内容，用于 AI 分析和评估。
2. **操作知识库节点**：通过 `wiki:node:move`、`wiki:node:retrieve` 和 `wiki:node:read` 权限，应用可以获取、移动和读取知识库节点，构建完整的知识库结构。
3. **访问知识空间**：通过 `wiki:space:read` 和 `wiki:space:retrieve` 权限，应用可以获取用户有权访问的所有知识空间信息。

### 配置步骤

1. 在您的飞书应用配置的"权限管理"页面，确保以上所有权限都已被添加并启用。
2. 在"安全设置"中配置重定向URI为：`http://localhost:3001/api/auth/callback`。这是应用处理飞书授权回调的地址。
3. 确保应用已通过飞书开放平台的审核，特别是涉及用户数据访问的权限。

### 注意事项

- 这些权限涉及用户数据访问，请在应用中明确告知用户数据用途，并获得用户明确授权。
- 应用应遵循最小权限原则，仅请求必要的权限范围。
- 用户可以在飞书设置中随时撤销已授予的权限。

请在您的飞书应用配置的“权限管理”页面，确保以上所有权限都已被添加并启用。

此外，请在“安全设置”中配置重定向URI为：`http://localhost:3001`。这是应用处理飞书授权回调的地址。

## ⚙️ 环境准备

在开始之前，请确保您的开发环境中已安装以下软件：

- [Node.js](https://nodejs.org/) (v14.x 或更高版本)
- [Python](https://www.python.org/) (v3.8 或更高版本)
- [npm](https://www.npmjs.com/) 或 [yarn](https://yarnpkg.com/)

## 🚀 安装与启动

### 1. 克隆项目

```bash
git clone <your-repository-url>
cd wikiNodeAI_demo
```

### 2. 后端配置

#### a. 创建并配置虚拟环境

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows
```

#### b. 安装依赖

```bash
pip install -r requirements.txt
```

#### c. 配置环境变量

在 `backend` 目录下，创建 `.env` 文件：

```bash
touch .env
```

然后，编辑 `.env` 文件，填入您的配置信息：

```ini
# Backend Environment Variables

# Feishu App Configuration
FEISHU_APP_ID=your_feishu_app_id_here
FEISHU_APP_SECRET=your_feishu_app_secret_here

# Flask App Configuration
FLASK_APP=app.py
FLASK_ENV=development

# Server Configuration
HOST=0.0.0.0
BACKEND_PORT=5001
HOSTNAME=localhost

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=logs/backend.log
MAX_LOG_SIZE=10  # 单个日志文件最大大小（MB）
BACKUP_COUNT=5   # 保留的备份文件数量
MAX_LOG_FILES=10 # 最多保留的日志文件总数

# Admin Configuration
ADMIN_TOKEN=admin-secret  # 管理员API访问令牌，请修改为强密码
```

### 3. 前端配置

#### a. 安装依赖

```bash
cd ../frontend
npm install
```

#### b. 配置环境变量

在 `frontend` 目录下，创建 `.env` 文件：

```bash
touch .env
```

然后，编辑 `.env` 文件，填入您的配置信息：

```ini
# Frontend Environment Variables

# Feishu App Configuration
REACT_APP_FEISHU_APP_ID=your_feishu_app_id_here
REACT_APP_FEISHU_APP_SECRET=your_feishu_app_secret_here

# Backend API Configuration
REACT_APP_BACKEND_URL=http://localhost:5001
REACT_APP_FRONTEND_PORT=3001
REACT_APP_HOSTNAME=localhost
REACT_APP_BACKEND_PORT=5001

# LLM API Configuration
# 请在此处设置你的大模型API Key，不要将真实的API Key提交到代码仓库
REACT_APP_LLM_API_KEY=your_llm_api_key_here

# Logging Configuration
REACT_APP_ENABLE_BACKEND_LOGGING=false
```

### 4. 启动应用

本项目提供了一个 `start.sh` 脚本来一键启动前后端服务。

```bash
./start.sh
```

该脚本会：
1. 在后台启动 Flask 后端服务（端口5001）。
2. 启动 React 前端开发服务器（端口3001）。
3. 自动清理可能占用端口的进程。

启动成功后，您可以在浏览器中访问 `http://localhost:3001` 来使用本应用。

### 5. 重新部署指南

如果需要重新部署应用，可以按照以下步骤操作：

1. 停止当前运行的服务
2. 清空项目目录
3. 重新克隆代码仓库
4. 重新安装前后端依赖
5. 启动应用

具体命令如下：

```bash
# 停止服务
ps aux | grep start.sh
kill -9 [PID]

# 清空目录并重新克隆
rm -rf wikiNodeAI_demo
git clone https://github.com/Chazzzz777/wikiNodeAI_demo.git
cd wikiNodeAI_demo

# 安装依赖
cd frontend && npm install
cd ../backend && pip install -r requirements.txt

# 启动应用
cd .. && ./start.sh
```

## 📖 使用说明

### 1. 登录

- 首次访问应用，会被引导至飞书授权登录页面。
- 使用您的飞书账号登录并授权。
- 授权成功后，应用将获取您的用户信息并展示知识空间列表。

### 2. 浏览知识库

- 在左侧的知识空间列表中，选择您想要操作的知识空间。
- 点击后，右侧将展示该知识库的完整节点树结构。

### 3. 文档导入 AI 分析

- 点击“导入文档 AI 评估”按钮，会弹出一个对话框。
- 输入一个飞书文档链接（支持 `docx`, `doc`, `wiki` 格式）。
- 输入您的 LLM API Key。
- （可选）选择模型、修改 Prompt 模板和占位符。
- 点击“开始分析”，右侧将实时展示 LLM 的分析结果。

### 4. 现有文档 AI 评估

- 在知识库节点树中，选中一个您想要评估的文档节点。
- 点击“当前文档 AI 评估”按钮。
- 输入您的 LLM API Key。
- （可选）修改 Prompt 模板。
- 点击“开始分析”，右侧将实时展示 LLM 的评估结果。

## 📝 API 端点

所有 API 均以 `/api` 为前缀。

- `POST /api/auth/token`: 使用授权码获取 `user_access_token`。
- `GET /api/wiki/spaces`: 获取知识空间列表。
- `GET /api/wiki/<space_id>/nodes/all`: 获取指定知识空间的全量节点树。
- `GET /api/wiki/doc/<obj_token>`: 获取文档的原始内容。
- `POST /api/llm/stream_analysis`: 对指定知识库节点进行流式 AI 分析。
- `POST /api/llm/doc_import_analysis`: 对导入的飞书文档进行流式 AI 分析。
- `GET /api/admin/logs/status`: (需认证) 获取日志系统状态。
- `POST /api/admin/logs/cleanup`: (需认证) 手动触发日志清理。

## 🪵 日志与监控

本项目的日志系统详细说明请参考 `backend/LOG_MANAGEMENT.md`。

- **日志位置**: `backend/logs/`
- **配置文件**: `backend/.env`
- **核心功能**:
    - 通过环境变量 `LOG_LEVEL` 控制日志级别。
    - `RotatingFileHandler` 实现日志轮转与清理。
    - 后台线程自动监控和清理日志。
- **管理**:
    - 使用 `GET /api/admin/logs/status` 查看状态。
    - 使用 `POST /api/admin/logs/cleanup` 手动清理。
    - 访问管理 API 需要在请求头中携带 `Authorization: Bearer <your_admin_token>`。

## 🔍 问题排查

- **401 Unauthorized 错误**:
    - 检查您的飞书 `user_access_token` 是否过期或无效。
    - 检查后端的 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 是否正确。
    - 对于管理 API，请检查 `ADMIN_TOKEN` 是否正确配置并携带。
- **前端无法连接到后端**:
    - 确认后端服务已在 `http://localhost:5001` (或您配置的端口) 正常运行。
    - 检查浏览器开发者工具的网络请求，看是否有跨域或其他网络错误。
- **LLM 请求失败**:
    - 检查您的 `OPENAI_API_KEY` 是否正确。
    - 检查后端日志 (`backend/logs/app.log`)，查看从 LLM 服务返回的具体错误信息。