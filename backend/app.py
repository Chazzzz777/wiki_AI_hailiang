import os
import requests
import json
import logging
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

load_dotenv() # Load environment variables from .env file

# --- Environment Variables ---
FRONTEND_PORT = os.getenv('REACT_APP_FRONTEND_PORT', 3001)
BACKEND_PORT = os.getenv('BACKEND_PORT', 5001)
FEISHU_APP_ID = os.getenv('FEISHU_APP_ID')
FEISHU_APP_SECRET = os.getenv('FEISHU_APP_SECRET')

app = Flask(__name__)
# 获取主机名环境变量，默认为localhost
HOSTNAME = os.getenv('HOSTNAME', 'localhost')
CORS(app, resources={r"/api/*": {"origins": [f"http://localhost:{FRONTEND_PORT}", f"http://{HOSTNAME}:{FRONTEND_PORT}", "http://localhost:3001"], "supports_credentials": True}})

# --- Logging Configuration ---
import os
from logging.handlers import RotatingFileHandler
import glob

# 确保日志目录存在
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 日志配置函数
def setup_logging():
    # 从环境变量获取日志级别，默认为INFO
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    
    # 日志轮转配置
    max_log_size = int(os.getenv('MAX_LOG_SIZE', '10')) * 1024 * 1024  # 默认10MB
    backup_count = int(os.getenv('BACKUP_COUNT', '5'))  # 默认保留5个备份
    max_log_files = int(os.getenv('MAX_LOG_FILES', '10'))  # 默认最多保留10个日志文件
    
    # 日志格式
    log_format = '%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d] %(message)s'
    formatter = logging.Formatter(log_format)
    
    # 清理过期的日志文件
    def cleanup_old_logs():
        try:
            log_files = glob.glob(os.path.join(log_dir, 'app.log.*'))
            log_files.extend(glob.glob(os.path.join(log_dir, 'app.log')))
            
            # 按修改时间排序
            log_files.sort(key=os.path.getmtime, reverse=True)
            
            # 删除超过最大数量的日志文件
            for log_file in log_files[max_log_files:]:
                try:
                    os.remove(log_file)
                    print(f"Deleted old log file: {log_file}")
                except Exception as e:
                    print(f"Failed to delete log file {log_file}: {e}")
        except Exception as e:
            print(f"Failed to cleanup old logs: {e}")
    
    # 执行清理
    cleanup_old_logs()
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_levels.get(log_level, logging.INFO))
    
    # 清除现有的处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_levels.get(log_level, logging.INFO))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 文件处理器（带轮转）
    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, 'app.log'),
        maxBytes=max_log_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(log_levels.get(log_level, logging.INFO))
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # 配置应用日志记录器
    app.logger.setLevel(log_levels.get(log_level, logging.INFO))
    
    # 记录日志配置信息
    app.logger.info(f"Logging configured - Level: {log_level}, Max size: {max_log_size//1024//1024}MB, Backups: {backup_count}, Max files: {max_log_files}")

# 初始化日志配置
setup_logging()

# --- 日志监控和清理任务 ---
import threading
import time

def log_monitor_task():
    """后台日志监控任务，定期检查日志状态并清理过期文件"""
    while True:
        try:
            # 每6小时执行一次清理
            time.sleep(6 * 60 * 60)
            app.logger.info("Running scheduled log cleanup task")
            
            # 重新执行日志清理
            setup_logging()
            
            # 检查日志目录大小
            log_dir_size = 0
            log_file_count = 0
            for root, dirs, files in os.walk(log_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        log_dir_size += os.path.getsize(file_path)
                        log_file_count += 1
                    except Exception as e:
                        app.logger.warning(f"Failed to get size of {file_path}: {e}")
            
            # 如果日志目录超过100MB，记录警告
            if log_dir_size > 100 * 1024 * 1024:
                app.logger.warning(f"Log directory size is {log_dir_size//1024//1024}MB with {log_file_count} files, consider adjusting log retention settings")
            else:
                app.logger.info(f"Log directory status: {log_dir_size//1024//1024}MB, {log_file_count} files")
                
        except Exception as e:
            app.logger.error(f"Error in log monitor task: {e}")
            # 出错后等待1小时再重试
            time.sleep(60 * 60)

# 启动日志监控线程（仅在生产环境）
if os.getenv('FLASK_ENV') != 'development':
    monitor_thread = threading.Thread(target=log_monitor_task, daemon=True)
    monitor_thread.start()
    app.logger.info("Started log monitor thread")

@app.route('/api/admin/logs/cleanup', methods=['POST'])
def manual_log_cleanup():
    """手动触发日志清理的管理接口"""
    try:
        # 简单的认证检查（生产环境中应该使用更严格的认证）
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Unauthorized"}), 401
        
        # 这里可以添加更复杂的权限检查
        # 现在只是简单的token验证
        token = auth_header.split(' ')[1]
        if token != os.getenv('ADMIN_TOKEN', 'admin-secret'):
            return jsonify({"error": "Invalid admin token"}), 401
        
        app.logger.info("Manual log cleanup triggered")
        
        # 执行日志清理
        before_cleanup = {}
        after_cleanup = {}
        
        # 清理前状态
        for root, dirs, files in os.walk(log_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(file_path)
                    before_cleanup[file_path] = size
                except Exception as e:
                    app.logger.warning(f"Failed to get size of {file_path}: {e}")
        
        # 重新设置日志配置（会触发清理）
        setup_logging()
        
        # 清理后状态
        for root, dirs, files in os.walk(log_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(file_path)
                    after_cleanup[file_path] = size
                except Exception as e:
                    app.logger.warning(f"Failed to get size of {file_path}: {e}")

        # 计算清理结果
        deleted_files = set(before_cleanup.keys()) - set(after_cleanup.keys())
        size_before = sum(before_cleanup.values())
        size_after = sum(after_cleanup.values())
        
        result = {
            "message": "Log cleanup completed",
            "deleted_files": list(deleted_files),
            "files_deleted_count": len(deleted_files),
            "size_before_mb": round(size_before / 1024 / 1024, 2),
            "size_after_mb": round(size_after / 1024 / 1024, 2),
            "space_freed_mb": round((size_before - size_after) / 1024 / 1024, 2)
        }
        
        app.logger.info(f"Manual cleanup result: {result}")
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Error in manual log cleanup: {e}")
        return jsonify({"error": str(e)}), 500

# 飞书API代理端点 - 解决CORS问题

# 通用飞书API代理端点
@app.route('/api/feishu/proxy', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def feishu_api_proxy():
    """通用飞书API代理端点，处理所有飞书API请求"""
    try:
        # 获取前端传递的用户token
        user_access_token = request.headers.get('Authorization')
        if not user_access_token or not user_access_token.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        
        user_access_token = user_access_token.split(' ')[1]
        
        # 获取请求方法、路径和查询参数
        method = request.method
        path = request.args.get('path', '')
        query_params = {}
        for key in request.args:
            if key != 'path':
                query_params[key] = request.args[key]
        
        # 获取请求数据
        data = request.get_json() if request.is_json else None
        
        # 构建完整的飞书API URL
        if not path:
            return jsonify({"error": "Missing path parameter"}), 400
        
        url = f'https://open.feishu.cn/open-apis{path}'
        if query_params:
            # 构建查询字符串
            query_string = '&'.join([f'{key}={value}' for key, value in query_params.items()])
            url = f'{url}?{query_string}'
        
        # 设置请求头
        headers = {
            'Authorization': f'Bearer {user_access_token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        # 记录请求信息
        app.logger.info(f'[飞书API代理] 通用代理请求: {method} {url}')
        app.logger.info(f'[飞书API代理] 请求头: {headers}')
        if data:
            app.logger.info(f'[飞书API代理] 请求数据: {data}')
        
        # 调用飞书API
        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'POST':
            response = requests.post(url, json=data, headers=headers)
        elif method == 'PUT':
            response = requests.put(url, json=data, headers=headers)
        elif method == 'PATCH':
            response = requests.patch(url, json=data, headers=headers)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers)
        
        # 使用通用函数记录请求响应信息
        log_request_response(url, headers, data, response, "通用代理")
        
        # 使用通用函数安全解析JSON响应
        try:
            result = safe_json_parse(response, "通用代理")
            return jsonify(result)
        except Exception:
            # 如果不是JSON响应，直接返回响应内容
            return Response(response.content, status=response.status_code, headers=dict(response.headers))
        
    except Exception as e:
        app.logger.error(f'[飞书API代理] 通用代理异常: {str(e)}')
        return jsonify({"error": f"请求失败: {str(e)}"}), 500

@app.route('/api/feishu/documents', methods=['POST'])
def create_feishu_document_proxy():
    """创建飞书文档的代理端点"""
    try:
        # 获取前端传递的用户token
        user_access_token = request.headers.get('Authorization')
        if not user_access_token or not user_access_token.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        
        user_access_token = user_access_token.split(' ')[1]
        
        # 获取请求数据
        data = request.get_json()
        if not data:
            app.logger.error('[飞书API代理] 创建文档请求缺少JSON数据')
            return jsonify({"error": "请求缺少JSON数据"}), 400
            
        title = data.get('title', '未命名文档')
        if not title or not isinstance(title, str):
            app.logger.error(f'[飞书API代理] 无效的文档标题: {title}')
            return jsonify({"error": "无效的文档标题"}), 400
        
        app.logger.info(f'[飞书API代理] 开始创建文档，标题: {title}')
        
        # 调用飞书API创建文档
        url = 'https://open.feishu.cn/open-apis/docx/v1/documents'
        headers = {
            'Authorization': f'Bearer {user_access_token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        request_data = {'title': title}
        response = requests.post(url, json=request_data, headers=headers)
        
        # 使用通用函数记录请求响应信息
        log_request_response(url, headers, request_data, response, "创建文档")
        
        # 使用通用函数安全解析JSON响应
        result = safe_json_parse(response, "创建文档")
        
        app.logger.info(f'[飞书API代理] 创建文档响应: {result}')
        
        if response.status_code != 200 or result.get('code') != 0:
            error_msg = result.get('msg', 'Unknown error')
            error_code = result.get('code', 'unknown')
            app.logger.error(f'[飞书API代理] 创建文档失败: {error_msg} (错误码: {error_code})')
            return jsonify({
                "error": f"创建文档失败: {error_msg}",
                "code": error_code
            }), response.status_code if response.status_code != 200 else 400
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f'[飞书API代理] 创建文档异常: {str(e)}')
        return jsonify({"error": f"创建文档失败: {str(e)}"}), 500

@app.route('/api/feishu/documents/<document_id>/blocks/convert', methods=['POST'])
def convert_markdown_to_blocks_proxy(document_id):
    """将Markdown转换为文档块的代理端点"""
    try:
        # 参数验证：确保document_id有效
        try:
            validate_document_id(document_id, "转换Markdown")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
            
        # 获取前端传递的用户token
        user_access_token = request.headers.get('Authorization')
        if not user_access_token or not user_access_token.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        
        user_access_token = user_access_token.split(' ')[1]
        
        # 获取请求数据
        data = request.get_json()
        if not data:
            app.logger.error('[飞书API代理] 转换Markdown请求缺少JSON数据')
            return jsonify({"error": "请求缺少JSON数据"}), 400
            
        markdown_content = data.get('content', '')
        if not isinstance(markdown_content, str):
            app.logger.error(f'[飞书API代理] 无效的Markdown内容类型: {type(markdown_content)}')
            return jsonify({"error": "Markdown内容必须是字符串类型"}), 400
        
        app.logger.info(f'[飞书API代理] 开始转换Markdown内容，长度: {len(markdown_content)}')
        app.logger.info(f'[飞书API代理] 转换前的Markdown原文: {markdown_content}')
        
        # 调用飞书API转换Markdown
        # 不进行转义处理，直接使用原始的Markdown内容
        url = 'https://open.feishu.cn/open-apis/docx/v1/documents/blocks/convert'
        headers = {
            'Authorization': f'Bearer {user_access_token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        request_data = {
            'content_type': 'markdown',
            'content': markdown_content
        }
        response = requests.post(url, json=request_data, headers=headers)
        
        # 使用通用函数记录请求响应信息
        log_request_response(url, headers, request_data, response, "转换Markdown")
        
        # 使用通用函数安全解析JSON响应
        result = safe_json_parse(response, "转换Markdown")
            
        app.logger.info(f'[飞书API代理] 转换响应: {result}')
        
        if response.status_code != 200 or result.get('code') != 0:
            error_msg = result.get('msg', 'Unknown error')
            error_code = result.get('code', 'unknown')
            app.logger.error(f'[飞书API代理] 转换内容失败: {error_msg} (错误码: {error_code})')
            return jsonify({
                "error": f"转换内容失败: {error_msg}",
                "code": error_code
            }), response.status_code if response.status_code != 200 else 400
        
        # 检查转换结果中的first_level_block_ids和blocks
        if 'data' in result:
            app.logger.info(f'[飞书API代理] 转换响应数据结构: {list(result["data"].keys())}')
            
            if 'first_level_block_ids' in result['data']:
                first_level_block_ids = result['data']['first_level_block_ids']
                app.logger.info(f'[飞书API代理] 首级块ID列表: {first_level_block_ids}')
            else:
                app.logger.warning(f'[飞书API代理] 转换结果中缺少first_level_block_ids字段')
                
            if 'blocks' in result['data']:
                blocks = result['data']['blocks']
                app.logger.info(f'[飞书API代理] 转换得到块数量: {len(blocks)}')
            else:
                app.logger.warning(f'[飞书API代理] 转换结果中缺少blocks字段')
                
            # 重要提示：first_level_block_ids和blocks的顺序必须保持不变
            # 在调用创建嵌套块接口时，first_level_block_ids对应children_id，blocks对应descendants
            app.logger.info(f'[飞书API代理] 重要提示：first_level_block_ids和blocks的顺序必须保持不变，以确保导出内容顺序一致')
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f'[飞书API代理] 转换内容异常: {str(e)}')
        return jsonify({"error": f"转换内容失败: {str(e)}"}), 500

@app.route('/api/feishu/documents/export-markdown', methods=['POST'])
def export_markdown_to_document_proxy():
    """将Markdown内容完整导出为飞书文档的代理端点（包含创建文档、转换Markdown、写入块的完整流程）"""
    try:
        # 1. 获取用户token和请求数据
        user_access_token = request.headers.get('Authorization')
        if not user_access_token or not user_access_token.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        
        user_access_token = user_access_token.split(' ')[1]
        
        data = request.get_json()
        if not data:
            app.logger.error('[飞书API代理] 导出Markdown请求缺少JSON数据')
            return jsonify({"error": "请求缺少JSON数据"}), 400
            
        title = data.get('title', '未命名文档')
        markdown_content = data.get('content', '')
        
        if not title or not isinstance(title, str):
            app.logger.error(f'[飞书API代理] 无效的文档标题: {title}')
            return jsonify({"error": "无效的文档标题"}), 400
            
        if not isinstance(markdown_content, str):
            app.logger.error(f'[飞书API代理] 无效的Markdown内容类型: {type(markdown_content)}')
            return jsonify({"error": "Markdown内容必须是字符串类型"}), 400
        
        # Markdown内容已经在前端处理好，不包含标题行
        
        app.logger.info(f'[飞书API代理] 开始导出Markdown为文档，标题: {title}, 内容长度: {len(markdown_content)}')
        
        # 2. 创建文档
        app.logger.info('[飞书API代理] 步骤1: 创建文档')
        create_url = 'https://open.feishu.cn/open-apis/docx/v1/documents'
        create_headers = {
            'Authorization': f'Bearer {user_access_token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        create_request_data = {'title': title}
        create_response = requests.post(create_url, json=create_request_data, headers=create_headers)
        
        # 使用通用函数记录请求响应信息
        log_request_response(create_url, create_headers, create_request_data, create_response, "创建文档")
        
        # 使用通用函数安全解析JSON响应
        create_result = safe_json_parse(create_response, "创建文档")
        
        if create_response.status_code != 200 or create_result.get('code') != 0:
            error_msg = create_result.get('msg', 'Unknown error')
            error_code = create_result.get('code', 'unknown')
            app.logger.error(f'[飞书API代理] 创建文档失败: {error_msg} (错误码: {error_code})')
            return jsonify({
                "error": f"创建文档失败: {error_msg}",
                "code": error_code
            }), create_response.status_code if create_response.status_code != 200 else 400
        
        document_id = create_result['data']['document']['document_id']
        app.logger.info(f'[飞书API代理] 文档创建成功，ID: {document_id}')
        
        # 3. 转换Markdown为文档块
        app.logger.info('[飞书API代理] 步骤2: 转换Markdown为文档块')
        
        # 调用飞书API转换Markdown
        # 不进行转义处理，直接使用原始的Markdown内容
        convert_url = 'https://open.feishu.cn/open-apis/docx/v1/documents/blocks/convert'
        convert_headers = {
            'Authorization': f'Bearer {user_access_token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        convert_request_data = {
            'content_type': 'markdown',
            'content': markdown_content
        }
        convert_response = requests.post(convert_url, json=convert_request_data, headers=convert_headers)
        
        # 使用通用函数记录请求响应信息
        log_request_response(convert_url, convert_headers, convert_request_data, convert_response, "转换Markdown")
        
        # 使用通用函数安全解析JSON响应
        convert_result = safe_json_parse(convert_response, "转换Markdown")
        
        if convert_response.status_code != 200 or convert_result.get('code') != 0:
            error_msg = convert_result.get('msg', 'Unknown error')
            error_code = convert_result.get('code', 'unknown')
            app.logger.error(f'[飞书API代理] 转换内容失败: {error_msg} (错误码: {error_code})')
            return jsonify({
                "error": f"转换内容失败: {error_msg}",
                "code": error_code
            }), convert_response.status_code if convert_response.status_code != 200 else 400
        
        # 检查转换结果中的first_level_block_ids和blocks
        if 'data' not in convert_result:
            app.logger.error(f'[飞书API代理] 转换结果中缺少data字段')
            return jsonify({"error": "转换结果格式错误：缺少data字段"}), 500
            
        if 'first_level_block_ids' not in convert_result['data']:
            app.logger.error(f'[飞书API代理] 转换结果中缺少first_level_block_ids字段')
            return jsonify({"error": "转换结果格式错误：缺少first_level_block_ids字段"}), 500
            
        if 'blocks' not in convert_result['data']:
            app.logger.error(f'[飞书API代理] 转换结果中缺少blocks字段')
            return jsonify({"error": "转换结果格式错误：缺少blocks字段"}), 500
        
        first_level_block_ids = convert_result['data']['first_level_block_ids']
        blocks = convert_result['data']['blocks']
        
        app.logger.info(f'[飞书API代理] 转换得到块数量: {len(blocks)}')
        app.logger.info(f'[飞书API代理] 首级块ID列表: {first_level_block_ids}')
        
        # 4. 将块写入文档
        app.logger.info('[飞书API代理] 步骤3: 将块写入文档')
        
        write_url = f'https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/descendant'
        write_headers = {
            'Authorization': f'Bearer {user_access_token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        write_request_data = {
            'children_id': first_level_block_ids,
            'descendants': blocks,
            'index': 0
        }
        write_response = requests.post(write_url, json=write_request_data, headers=write_headers)
        
        # 使用通用函数记录请求响应信息
        log_request_response(write_url, write_headers, write_request_data, write_response, "写入文档")
        
        # 使用通用函数安全解析JSON响应
        write_result = safe_json_parse(write_response, "写入文档")
        
        if write_response.status_code != 200 or write_result.get('code') != 0:
            error_msg = write_result.get('msg', 'Unknown error')
            error_code = write_result.get('code', 'unknown')
            app.logger.error(f'[飞书API代理] 写入文档失败: {error_msg} (错误码: {error_code})')
            return jsonify({
                "error": f"写入文档失败: {error_msg}",
                "code": error_code
            }), write_response.status_code if write_response.status_code != 200 else 400
        
        # 5. 返回最终结果
        document_url = f'https://feishu.cn/docx/{document_id}'
        app.logger.info(f'[飞书API代理] Markdown导出完成，文档URL: {document_url}')
        
        return jsonify({
            "data": {
                "documentId": document_id,
                "documentUrl": document_url,
                "title": title
            }
        })
        
    except Exception as e:
        app.logger.error(f'[飞书API代理] 导出Markdown异常: {str(e)}')
        return jsonify({"error": f"导出失败: {str(e)}"}), 500

@app.route('/api/feishu/documents/<document_id>/blocks/<block_id>/descendant', methods=['POST'])
def write_blocks_to_document_proxy(document_id, block_id):
    """将文档块写入飞书文档的代理端点（支持分批处理、表格和图片处理）"""
    try:
        # 1. 参数验证和Token获取
        try:
            validate_document_id(document_id, "写入文档")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        
        user_access_token = request.headers.get('Authorization')
        if not user_access_token or not user_access_token.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        user_access_token = user_access_token.split(' ')[1]
        
        # 2. 获取和预处理块数据
        data = request.get_json()
        blocks = data.get('descendants', [])
        first_level_block_ids = data.get('first_level_block_ids', [])

        if not isinstance(blocks, list):
            blocks = []
        
        app.logger.info(f'[飞书API代理] 开始写入文档块，总数量: {len(blocks)}')

        # 创建 block_id 到 block 对象的映射，方便快速查找
        block_map = {block.get('block_id'): block for block in blocks}

        # 如果前端没有提供 first_level_block_ids，则从所有块中推断
        if not first_level_block_ids:
            app.logger.info("[飞书API代理] 前端未提供 first_level_block_ids，开始推断顶级块...")
            all_child_ids = set()
            for block in blocks:
                all_child_ids.update(block.get('children', []))
            
            # 保持原始顺序
            inferred_top_level_ids = [
                block.get('block_id') for block in blocks 
                if block.get('block_id') not in all_child_ids
            ]
            first_level_block_ids = inferred_top_level_ids
            app.logger.info(f"[飞书API代理] 推断出的顶级块ID: {first_level_block_ids}")

        # 3. 识别图片块并处理表格
        image_blocks = []
        for block_id_key in block_map:
            block = block_map[block_id_key]
            if block.get('block_type') == 27: # Image
                image_blocks.append({'block_id': block.get('block_id')})
                app.logger.info(f'[飞书API代理] 发现图片块，block_id: {block.get("block_id")}')
            
            if block.get('block_type') == 31: # Table
                if 'table' in block and 'property' in block.get('table', {}) and 'merge_info' in block.get('table', {}).get('property', {}):
                    app.logger.info(f'[飞书API代理] 去除表格块merge_info字段: {block.get("block_id")}')
                    del block['table']['property']['merge_info']

        # 4. 构建批处理任务
        # 这个函数递归地获取一个块的所有子孙块
        def get_all_descendants_recursive(start_block_id, block_map, visited_ids):
            if start_block_id in visited_ids:
                return []
            
            visited_ids.add(start_block_id)
            
            if start_block_id not in block_map:
                return []

            block = block_map[start_block_id]
            subtree_blocks = [block]
            
            for child_id in block.get('children', []):
                subtree_blocks.extend(get_all_descendants_recursive(child_id, block_map, visited_ids))
            return subtree_blocks

        # 构建批次，确保父子关系不被破坏
        batches = []
        current_batch_blocks = []
        current_batch_children_ids = []
        BATCH_SIZE = 1000
        processed_top_level_ids = set()

        for top_level_id in first_level_block_ids:
            if top_level_id in processed_top_level_ids:
                continue

            subtree = get_all_descendants_recursive(top_level_id, block_map, processed_top_level_ids)
            
            # 如果当前子树加入后超过批次大小，则先处理当前批次
            if len(current_batch_blocks) + len(subtree) > BATCH_SIZE and current_batch_blocks:
                batches.append({
                    "children_id": current_batch_children_ids,
                    "descendants": current_batch_blocks
                })
                current_batch_blocks = []
                current_batch_children_ids = []

            # 将当前子树的所有块加入批次
            current_batch_blocks.extend(subtree)
            current_batch_children_ids.append(top_level_id)

        # 添加最后一个批次
        if current_batch_blocks:
            batches.append({
                "children_id": current_batch_children_ids,
                "descendants": current_batch_blocks
            })

        # 5. 执行批处理写入
        all_results = []
        total_batches = len(batches)
        for i, batch in enumerate(batches):
            batch_num = i + 1
            app.logger.info(f'[飞书API代理] 处理第 {batch_num}/{total_batches} 批，块数量: {len(batch["descendants"])}')
            
            # 验证父子关系
            validate_block_parent_child_relationships(batch["descendants"])

            # 准备API请求
            url = f'https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/descendant'
            headers = {
                'Authorization': f'Bearer {user_access_token}',
                'Content-Type': 'application/json; charset=utf-8'
            }
            request_data = {
                'children_id': batch['children_id'],
                'descendants': batch['descendants'],
                'index': data.get('index', -1)
            }

            # 发送请求
            response = requests.post(url, json=request_data, headers=headers)
            log_request_response(url, headers, request_data, response, f"写入文档第{batch_num}批")
            result = safe_json_parse(response, f"写入文档第{batch_num}批")
            
            app.logger.info(f'[飞书API代理] 第 {batch_num} 批写入响应: {result}')
            
            if response.status_code != 200 or result.get('code') != 0:
                error_msg = result.get('msg', 'Unknown error')
                error_code = result.get('code', 'unknown')
                app.logger.error(f'[飞书API代理] 第 {batch_num} 批写入失败: {error_msg} (错误码: {error_code})')
                return jsonify({
                    "error": f"第 {batch_num} 批写入失败: {error_msg}",
                    "code": error_code,
                    "batch_number": batch_num
                }), response.status_code if response.status_code != 200 else 400
            
            all_results.append(result)

        # 6. 处理图片块上传和更新
        image_update_results = []
        for image_info in image_blocks:
            try:
                image_result = process_image_upload_and_update(
                    document_id, 
                    image_info['block_id'], 
                    user_access_token
                )
                image_update_results.append(image_result)
                app.logger.info(f'[飞书API代理] 图片块处理完成: {image_info["block_id"]}')
            except Exception as e:
                app.logger.error(f'[飞书API代理] 图片块处理失败: {image_info["block_id"]}, 错误: {str(e)}')
                image_update_results.append({
                    "block_id": image_info['block_id'],
                    "error": str(e)
                })
        
        # 7. 返回最终结果
        document_url = f'https://feishu.cn/docx/{document_id}'
        return jsonify({
            "data": {
                "documentId": document_id,
                "documentUrl": document_url,
                "total_blocks": len(blocks),
                "batches_processed": total_batches,
                "image_blocks_processed": len(image_blocks),
                "batch_results": all_results,
                "image_update_results": image_update_results
            }
        })

    except Exception as e:
        app.logger.error(f'[飞书API代理] 写入文档异常: {str(e)}')
        return jsonify({"error": f"写入文档失败: {str(e)}"}), 500

def process_image_upload_and_update(document_id, image_block_id, user_access_token):
    """处理图片上传和块更新的函数"""
    try:
        # 第一步：上传图片素材
        upload_url = 'https://open.feishu.cn/open-apis/docx/v1/images/upload'
        headers = {
            'Authorization': f'Bearer {user_access_token}',
        }
        
        # 注意：这里需要实际的图片文件数据，当前示例中我们假设有图片数据
        # 在实际应用中，需要从前端传递图片文件或图片URL
        # 这里创建一个占位符图片数据（1x1像素的透明PNG）
        import base64
        placeholder_image_data = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI/hjBMqQAAAABJRU5ErkJggg==')
        
        # 上传图片素材
        files = {'file': ('placeholder.png', placeholder_image_data, 'image/png')}
        
        upload_response = requests.post(upload_url, headers=headers, files=files)
        
        # 使用通用函数记录请求响应信息
        log_request_response(upload_url, headers, None, upload_response, "图片上传")
        
        # 使用通用函数安全解析JSON响应
        upload_result = safe_json_parse(upload_response, "图片上传")
        
        if upload_response.status_code != 200 or upload_result.get('code') != 0:
            raise Exception(f"图片上传失败: {upload_result.get('msg', 'Unknown error')}")
        
        image_material_id = upload_result['data']['image_id']
        app.logger.info(f'[飞书API代理] 图片素材上传成功，material_id: {image_material_id}')
        
        # 第二步：更新图片块，替换图片
        update_url = f'https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{image_block_id}'
        update_headers = {
            'Authorization': f'Bearer {user_access_token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        update_payload = {
            "requests": [{
                "replace_image": {
                    "image_id": image_material_id
                }
            }]
        }
        
        update_response = requests.patch(update_url, headers=update_headers, json=update_payload)
        
        # 使用通用函数记录请求响应信息
        log_request_response(update_url, update_headers, update_payload, update_response, "图片更新")
        
        # 使用通用函数安全解析JSON响应
        update_result = safe_json_parse(update_response, "图片更新")
        
        if update_response.status_code != 200 or update_result.get('code') != 0:
            raise Exception(f"图片块更新失败: {update_result.get('msg', 'Unknown error')}")
        
        app.logger.info(f'[飞书API代理] 图片块更新成功: {image_block_id}')
        
        return {
            "block_id": image_block_id,
            "image_material_id": image_material_id,
            "status": "success"
        }
            
    except Exception as e:
        app.logger.error(f'[飞书API代理] 图片处理异常: {str(e)}')
        raise e

@app.route('/api/admin/logs/status', methods=['GET'])
def get_log_status():
    """获取日志状态信息"""
    try:
        # 简单的认证检查
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Unauthorized"}), 401
        
        token = auth_header.split(' ')[1]
        if token != os.getenv('ADMIN_TOKEN', 'admin-secret'):
            return jsonify({"error": "Invalid admin token"}), 401
        
        # 收集日志状态信息
        log_files = []
        total_size = 0
        
        for root, dirs, files in os.walk(log_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    stat = os.stat(file_path)
                    file_info = {
                        "name": file,
                        "path": file_path,
                        "size_bytes": stat.st_size,
                        "size_mb": round(stat.st_size / 1024 / 1024, 2),
                        "modified": stat.st_mtime,
                        "created": stat.st_ctime
                    }
                    log_files.append(file_info)
                    total_size += stat.st_size
                except Exception as e:
                    app.logger.warning(f"Failed to get info for {file_path}: {e}")
        
        # 按修改时间排序
        log_files.sort(key=lambda x: x['modified'], reverse=True)
        
        status = {
            "log_directory": log_dir,
            "total_files": len(log_files),
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "log_files": log_files[:20],  # 只返回最新的20个文件信息
            "config": {
                "log_level": os.getenv('LOG_LEVEL', 'INFO'),
                "max_log_size_mb": int(os.getenv('MAX_LOG_SIZE', '10')),
                "backup_count": int(os.getenv('BACKUP_COUNT', '5')),
                "max_log_files": int(os.getenv('MAX_LOG_FILES', '10'))
            }
        }
        
        return jsonify(status)
        
    except Exception as e:
        app.logger.error(f"Error getting log status: {e}")
        return jsonify({"error": str(e)}), 500

# --- Global Request Logger ---

@app.before_request
def log_request_info():
    app.logger.info('--- Incoming Request ---')
    app.logger.info(f'Method: {request.method}')
    app.logger.info(f'Path: {request.path}')
    app.logger.info(f'Headers: {request.headers}')

# --- Helper Functions ---

def safe_json_parse(response, operation_name="API调用"):
    """安全地解析JSON响应，提供详细的错误日志
    
    Args:
        response: requests.Response对象
        operation_name: 操作名称，用于日志记录
        
    Returns:
        dict: 解析后的JSON数据
        
    Raises:
        Exception: 当JSON解析失败时抛出异常
    """
    try:
        result = response.json()
        return result
    except ValueError as json_error:
        app.logger.error(f'[飞书API代理] {operation_name} JSON解析失败: {str(json_error)}')
        app.logger.error(f'[飞书API代理] {operation_name} 响应状态码: {response.status_code}')
        app.logger.error(f'[飞书API代理] {operation_name} 响应内容类型: {response.headers.get("content-type", "unknown")}')
        app.logger.error(f'[飞书API代理] {operation_name} 原始响应内容: {response.text}')
        raise Exception(f"{operation_name} API返回了非JSON格式的响应，状态码: {response.status_code}")

def validate_document_id(document_id, operation_name="操作"):
    """验证document_id参数的有效性
    
    Args:
        document_id: 要验证的文档ID
        operation_name: 操作名称，用于错误消息
        
    Returns:
        bool: 如果验证通过返回True，否则返回False
        
    Raises:
        ValueError: 当document_id无效时抛出异常
    """
    if not document_id or document_id == 'undefined' or not isinstance(document_id, str):
        error_msg = f"无效的document_id参数: {document_id}"
        app.logger.error(f'[飞书API代理] {operation_name}时{error_msg}')
        raise ValueError(error_msg)
    return True

def validate_block_parent_child_relationships(blocks):
    """验证块的父子关系是否合法
    
    Args:
        blocks: 块对象列表
    """
    # 定义块类型映射
    BLOCK_TYPE_MAP = {
        1: 'page',
        2: 'text',
        3: 'heading1',
        4: 'heading2',
        5: 'heading3',
        6: 'heading4',
        7: 'heading5',
        8: 'heading6',
        9: 'heading7',
        10: 'heading8',
        11: 'heading9',
        12: 'bullet',
        13: 'ordered',
        14: 'code',
        15: 'quote',
        16: 'equation',
        17: 'todo',
        18: 'divider',
        19: 'file',
        20: 'gallery',
        21: 'web',
        22: 'video',
        23: 'table',
        24: 'table_cell',
        25: 'view',
        26: 'grid',
        27: 'image',
        28: 'grid_column',
        29: 'quote_container',
        30: 'callout',
        31: 'chat_card',
        32: 'diagram',
        33: 'iframe',
        34: 'bitable',
        35: 'sheet',
        36: 'mindnote',
        37: 'board',
        38: 'synced_source',
        39: 'synced_reference',
        40: 'undefined'
    }
    
    # 定义合法的父子关系
    # key: 父块类型, value: 允许的子块类型列表
    LEGAL_PARENT_CHILD_RELATIONSHIPS = {
        'callout': ['text', 'heading1', 'heading2', 'heading3', 'heading4', 'heading5', 'heading6', 'heading7', 'heading8', 'heading9', 'ordered', 'bullet', 'todo', 'quote', 'quote_container'],
        'quote_container': ['text', 'heading1', 'heading2', 'heading3', 'heading4', 'heading5', 'heading6', 'heading7', 'heading8', 'heading9', 'ordered', 'bullet', 'todo', 'quote', 'quote_container'],
        'grid_column': ['text', 'heading1', 'heading2', 'heading3', 'heading4', 'heading5', 'heading6', 'heading7', 'heading8', 'heading9', 'ordered', 'bullet', 'todo', 'quote', 'quote_container', 'callout', 'image', 'file', 'web', 'video', 'bitable', 'sheet', 'mindnote', 'board', 'diagram', 'iframe', 'synced_source', 'synced_reference'],
        'table_cell': ['text', 'heading1', 'heading2', 'heading3', 'heading4', 'heading5', 'heading6', 'heading7', 'heading8', 'heading9', 'ordered', 'bullet', 'todo', 'quote', 'quote_container', 'callout', 'image', 'file', 'web', 'video', 'bitable', 'sheet', 'mindnote', 'board', 'diagram', 'iframe', 'synced_source', 'synced_reference'],
        # 其他块类型默认允许所有子块
    }
    
    # 创建块ID到块对象的映射，方便查找
    block_id_to_block = {block.get('block_id'): block for block in blocks}
    
    for block in blocks:
        parent_type = BLOCK_TYPE_MAP.get(block.get('block_type'), 'unknown')
        children_ids = block.get('children', [])
        
        # 检查每个子块
        for child_id in children_ids:
            child_block = block_id_to_block.get(child_id)
            if not child_block:
                # 如果找不到子块，跳过验证
                continue
            
            child_type = BLOCK_TYPE_MAP.get(child_block.get('block_type'), 'unknown')
            
            # 检查父子关系是否合法
            allowed_children = LEGAL_PARENT_CHILD_RELATIONSHIPS.get(parent_type)
            if allowed_children and child_type not in allowed_children:
                app.logger.warning(f'[飞书API代理] 块父子关系不合法: 父块类型 {parent_type} ({block.get("block_id")}) 不能包含子块类型 {child_type} ({child_id})')

def log_request_response(url, headers, request_data, response, operation_name):
    """记录请求和响应的详细信息
    
    Args:
        url: 请求URL
        headers: 请求头
        request_data: 请求数据（可选）
        response: 响应对象（可选）
        operation_name: 操作名称
    """
    app.logger.info(f'[飞书API代理] {operation_name}请求URL: {url}')
    app.logger.info(f'[飞书API代理] {operation_name}请求头: {headers}')
    
    if request_data is not None:
        if isinstance(request_data, dict):
            # 对于字典类型，记录键和大小信息，避免敏感数据泄露
            safe_data = {k: len(str(v)) if isinstance(v, (str, list, dict)) else type(v).__name__ for k, v in request_data.items()}
            app.logger.info(f'[飞书API代理] {operation_name}请求数据: {safe_data}')
        else:
            app.logger.info(f'[飞书API代理] {operation_name}请求数据长度: {len(str(request_data))}')
    
    if response is not None:
        app.logger.info(f'[飞书API代理] {operation_name}响应状态码: {response.status_code}')
        app.logger.info(f'[飞书API代理] {operation_name}响应头: {dict(response.headers)}')
        # 限制响应内容长度，避免日志过大
        response_content = response.text
        if len(response_content) > 500:
            app.logger.info(f'[飞书API代理] {operation_name}响应内容: {response_content[:500]}...')
        else:
            app.logger.info(f'[飞书API代理] {operation_name}响应内容: {response_content}')

def get_user_access_token(code, redirect_uri):
    """获取飞书用户访问令牌
    
    Args:
        code: 授权码
        redirect_uri: 重定向URI，必须与授权请求中的一致
        
    Returns:
        str: 访问令牌，如果获取失败则返回None
    """
    # 验证输入参数
    if not code or not isinstance(code, str):
        app.logger.error(f"Invalid code parameter: {code}")
        return None
        
    if not redirect_uri or not isinstance(redirect_uri, str):
        app.logger.error(f"Invalid redirect_uri parameter: {redirect_uri}")
        return None
    
    # 检查必要的环境变量
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        app.logger.error("Feishu app credentials not configured properly")
        return None
    
    url = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": FEISHU_APP_ID,
        "client_secret": FEISHU_APP_SECRET,
        "redirect_uri": redirect_uri
    }
    headers = {
        "Content-Type": "application/json"
    }

    app.logger.info("="*20 + " Feishu user_access_token Request " + "="*20)
    app.logger.info(f"POST {url}")
    app.logger.info("HEADERS: " + json.dumps(headers, indent=2))
    # 不记录完整的payload，避免敏感信息泄露
    safe_payload = {k: v if k not in ['client_secret', 'code'] else '***' for k, v in payload.items()}
    app.logger.info("BODY: " + json.dumps(safe_payload, indent=2))
    app.logger.info("="*60)

    try:
        response = requests.post(url, json=payload, headers=headers)
        app.logger.info("--- Received response from Feishu ---")
        app.logger.info(f"Status Code: {response.status_code}")
        # 只记录响应状态码，不记录完整响应内容，避免敏感信息泄露
        
        response.raise_for_status()
        data = response.json()
        
        # 检查飞书API返回的错误码
        if data.get("code", -1) != 0:
            error_msg = data.get("msg", "Unknown error")
            app.logger.error(f"Failed to get user_access_token from feishu: {error_msg} (code: {data.get('code')})")
            return None
            
        access_token = data.get("access_token")
        if not access_token:
            app.logger.error("No access_token in feishu response")
            return None
            
        app.logger.info("Successfully obtained user_access_token from feishu")
        return access_token
        
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request error while getting user_access_token: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            app.logger.error(f"Response status: {e.response.status_code}")
            # 尝试记录飞书API返回的错误信息，帮助排查问题
            try:
                error_data = e.response.json()
                app.logger.error(f"Feishu API error response: {json.dumps(error_data)}")
            except ValueError:
                app.logger.error("Failed to parse error response as JSON")
        return None
    except ValueError as e:
        app.logger.error(f"JSON parsing error while getting user_access_token: {str(e)}")
        return None
    except Exception as e:
        app.logger.error(f"Unexpected error while getting user_access_token: {str(e)}")
        return None


# --- API Routes ---

@app.route('/api/auth/callback')
def auth_callback():
    """处理飞书授权回调
    
    该端点接收飞书授权服务器的回调，获取授权码，
    然后将用户重定向回前端应用，并传递授权码。
    """
    try:
        # 获取授权码
        code = request.args.get('code')
        
        # 检查是否有错误参数
        error = request.args.get('error')
        error_description = request.args.get('error_description')
        
        if error:
            app.logger.error(f"Authorization error: {error}, description: {error_description}")
            # 重定向到前端错误页面
            frontend_url = f"http://localhost:{FRONTEND_PORT}/auth-error"
            return f'<script>window.location.href = "{frontend_url}?error={error}&description={error_description}";</script>'
        
        # 验证授权码
        if not code:
            app.logger.error("No authorization code received in callback")
            frontend_url = f"http://localhost:{FRONTEND_PORT}/auth-error"
            return f'<script>window.location.href = "{frontend_url}?error=missing_code&description=No+authorization+code+received";</script>'
        
        # 记录授权码接收成功（不记录完整授权码，避免敏感信息泄露）
        app.logger.info(f"Received authorization code (length: {len(code)})")
        
        # 从环境变量获取前端URL，如果没有则使用默认值
        # 使用HOSTNAME环境变量作为主机名，确保与前端配置一致
        hostname = os.getenv('HOSTNAME', 'localhost')
        frontend_base_url = os.getenv('FRONTEND_BASE_URL', f"http://{hostname}:{FRONTEND_PORT}")
        
        # 构建重定向URL，确保URL格式正确，重定向到根路径（不带末尾的/）
        redirect_url = f"{frontend_base_url}?code={code}"
        
        app.logger.info(f"Redirecting to frontend: {frontend_base_url}")
        
        # 使用JavaScript重定向，确保在浏览器中正确执行
        return f'<script>window.location.href = "{redirect_url}";</script>'
        
    except Exception as e:
        app.logger.error(f"Unexpected error in auth_callback: {str(e)}")
        # 发生错误时重定向到前端错误页面
        frontend_url = f"http://localhost:{FRONTEND_PORT}/auth-error"
        return f'<script>window.location.href = "{frontend_url}?error=server_error&description=Internal+server+error";</script>'

@app.route('/api/auth/url', methods=['GET'])
def get_auth_url():
    """获取飞书授权URL
    
    该端点返回飞书授权URL，前端可以使用此URL
    将用户重定向到飞书进行授权。
    """
    try:
        # 检查必要的环境变量
        if not FEISHU_APP_ID:
            app.logger.error("Feishu app ID not configured")
            return jsonify({"error": "Feishu app not configured properly"}), 500
            
        # 获取前端基础URL
        frontend_base_url = os.getenv('FRONTEND_BASE_URL', f"http://localhost:{FRONTEND_PORT}")
        
        # 构建回调URL
        callback_url = f"{frontend_base_url}/api/auth/callback"
        
        # 构建飞书授权URL
        auth_url = (
            f"https://open.feishu.cn/open-apis/authen/v1/authorize"
            f"?app_id={FEISHU_APP_ID}"
            f"&redirect_uri={callback_url}"
            f"&state={os.urandom(16).hex()}"  # 添加随机state参数，防止CSRF攻击
        )
        
        app.logger.info(f"Generated auth URL with callback: {callback_url}")
        
        return jsonify({
            "auth_url": auth_url,
            "callback_url": callback_url
        })
        
    except Exception as e:
        app.logger.error(f"Unexpected error in get_auth_url: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/auth/error', methods=['GET'])
def auth_error():
    """处理授权错误页面
    
    该端点处理授权过程中出现的错误，
    返回一个简单的错误页面，显示错误信息。
    """
    try:
        # 获取错误参数
        error = request.args.get('error', 'unknown_error')
        description = request.args.get('description', 'An unknown error occurred during authentication')
        
        # 记录错误
        app.logger.error(f"Authentication error: {error}, description: {description}")
        
        # 返回简单的错误页面
        error_page = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Authentication Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .error-container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9; }}
                h1 {{ color: #d32f2f; }}
                p {{ margin-bottom: 15px; }}
                .back-button {{ display: inline-block; padding: 10px 15px; background-color: #2196f3; color: white; text-decoration: none; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <div class="error-container">
                <h1>Authentication Error</h1>
                <p><strong>Error:</strong> {error}</p>
                <p><strong>Description:</strong> {description}</p>
                <p>Please try again or contact support if the problem persists.</p>
                <a href="/" class="back-button">Back to Home</a>
            </div>
        </body>
        </html>
        """
        
        return error_page
        
    except Exception as e:
        app.logger.error(f"Unexpected error in auth_error: {str(e)}")
        return "Internal Server Error", 500

@app.route('/api/auth/validate', methods=['POST'])
def validate_token():
    """验证访问令牌的有效性
    
    该端点验证提供的访问令牌是否仍然有效，
    并返回用户信息（如果令牌有效）。
    """
    try:
        # 获取授权头
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
            
        user_access_token = auth_header.split(' ')[1]
        
        # 验证令牌格式
        if not user_access_token or not isinstance(user_access_token, str):
            return jsonify({"error": "Invalid token format"}), 401
            
        # 调用飞书API验证令牌
        url = "https://open.feishu.cn/open-apis/authen/v1/user_info"
        headers = {
            "Authorization": f"Bearer {user_access_token}",
            "Content-Type": "application/json"
        }
        
        app.logger.info(f"Validating token (length: {len(user_access_token)})")
        
        response = requests.get(url, headers=headers)
        
        # 检查响应状态
        if response.status_code != 200:
            app.logger.error(f"Token validation failed with status: {response.status_code}")
            return jsonify({"error": "Invalid or expired token"}), 401
            
        # 解析响应
        data = response.json()
        if data.get("code", -1) != 0:
            error_msg = data.get("msg", "Unknown error")
            app.logger.error(f"Token validation failed: {error_msg} (code: {data.get('code')})")
            return jsonify({"error": "Invalid or expired token"}), 401
            
        # 提取用户信息
        user_info = data.get("data", {})
        
        app.logger.info(f"Token validated successfully for user: {user_info.get('name', 'unknown')}")
        
        # 返回用户信息（不包含敏感信息）
        safe_user_info = {
            "user_id": user_info.get("user_id"),
            "name": user_info.get("name"),
            "en_name": user_info.get("en_name"),
            "avatar": user_info.get("avatar_url")
        }
        
        return jsonify({
            "valid": True,
            "user": safe_user_info
        })
        
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request error while validating token: {str(e)}")
        return jsonify({"error": "Failed to validate token"}), 500
        
    except Exception as e:
        app.logger.error(f"Unexpected error in validate_token: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/auth/token', methods=['POST'])
def get_token():
    """使用授权码获取飞书访问令牌
    
    该端点接收前端发送的授权码和重定向URI，
    然后向飞书API请求访问令牌，并返回给前端。
    """
    app.logger.info("--- Received /api/auth/token request ---")
    
    # 打印授权相关的环境变量和配置信息
    app.logger.info("=== 授权相关配置信息 ===")
    app.logger.info(f"后端端口: {BACKEND_PORT}")
    app.logger.info(f"前端端口: {FRONTEND_PORT}")
    app.logger.info(f"主机名: {os.getenv('HOSTNAME', 'localhost')}")
    app.logger.info(f"飞书应用ID: {FEISHU_APP_ID}")
    app.logger.info("CORS配置: 已启用CORS支持")
    app.logger.info(f"请求来源: {request.remote_addr}")
    app.logger.info(f"请求头: {dict(request.headers)}")
    app.logger.info("=========================")
    
    try:
        # 获取请求数据
        data = request.get_json()
        if not data:
            app.logger.error("No JSON data received in request")
            return jsonify({"error": "Request must include JSON data"}), 400
            
        # 记录请求数据（不记录敏感信息）
        safe_data = {k: v if k != 'code' else '***' for k, v in data.items()}
        app.logger.info(f"Request data: {safe_data}")
        
        # 提取并验证参数
        code = data.get('code')
        redirect_uri = data.get('redirect_uri')
        
        # 验证必要参数
        if not code:
            app.logger.error("Missing required parameter: code")
            return jsonify({"error": "Code is required"}), 400
            
        if not redirect_uri:
            app.logger.error("Missing required parameter: redirect_uri")
            return jsonify({"error": "Redirect URI is required"}), 400
            
        # 验证参数类型
        if not isinstance(code, str):
            app.logger.error(f"Invalid code type: {type(code)}")
            return jsonify({"error": "Code must be a string"}), 400
            
        if not isinstance(redirect_uri, str):
            app.logger.error(f"Invalid redirect_uri type: {type(redirect_uri)}")
            return jsonify({"error": "Redirect URI must be a string"}), 400
            
        # 验证redirect_uri格式
        if not redirect_uri.startswith(('http://', 'https://')):
            app.logger.error(f"Invalid redirect_uri format: {redirect_uri}")
            return jsonify({"error": "Redirect URI must be a valid URL"}), 400
            
        app.logger.info(f"Extracted code (length: {len(code)})")
        app.logger.info(f"Extracted redirect_uri: {redirect_uri}")
        
        # 获取访问令牌
        user_access_token = get_user_access_token(code, redirect_uri)
        
        if not user_access_token:
            app.logger.error("Failed to get user_access_token")
            return jsonify({"error": "Failed to get access token"}), 500
            
        # 成功获取令牌
        app.logger.info("Successfully obtained user_access_token")
        response_data = {
            "user_access_token": user_access_token,
            "token_type": "Bearer"
        }
        return jsonify(response_data)
        
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request error while getting token: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            app.logger.error(f"Response status: {e.response.status_code}")
            # 不记录完整的响应内容，避免敏感信息泄露
            
            # 尝试解析错误响应
            try:
                error_data = e.response.json()
                return jsonify({"error": error_data}), e.response.status_code
            except (ValueError, AttributeError):
                return jsonify({"error": "Failed to communicate with Feishu API"}), e.response.status_code if hasattr(e, 'response') and e.response is not None else 500
        else:
            return jsonify({"error": "Failed to communicate with Feishu API"}), 500
            
    except Exception as e:
        app.logger.error(f"Unexpected error in get_token: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

# 速率限制器
class RateLimiter:
    def __init__(self, max_calls, per_seconds):
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self.calls = []
        # 添加安全系数，实际限制比理论值更严格
        self.safety_factor = 0.8  # 只使用80%的理论限制
        self.effective_max_calls = int(max_calls * self.safety_factor)
        self.counter = 0  # 用于生成唯一函数名

    def __call__(self, f):
        # 为每个装饰的函数生成唯一的wrapped函数名，避免Flask端点冲突
        def wrapped(*args, **kwargs):
            now = time.time()
            # 移除指定时间前的调用记录
            self.calls = [c for c in self.calls if c > now - self.per_seconds]
            
            # 使用更严格的有效限制
            if len(self.calls) >= self.effective_max_calls:
                # 计算需要等待的时间
                sleep_time = (self.calls[0] + self.per_seconds) - now
                if sleep_time > 0:
                    # 添加额外缓冲时间
                    buffer_time = 0.5
                    total_sleep = sleep_time + buffer_time
                    app.logger.warning(f"Rate limit reached (effective: {self.effective_max_calls}/{self.max_calls}). Sleeping for {total_sleep:.2f} seconds.")
                    time.sleep(total_sleep)
            
            # 记录请求时间
            self.calls.append(time.time())
            
            # 添加小延迟确保请求间隔
            if len(self.calls) > 1:
                time_since_last = now - self.calls[-2]
                min_interval = self.per_seconds / self.effective_max_calls
                if time_since_last < min_interval:
                    additional_delay = min_interval - time_since_last
                    app.logger.debug(f"Adding delay {additional_delay:.3f}s to maintain rate limit")
                    time.sleep(additional_delay)
            
            return f(*args, **kwargs)
        
        # 为wrapped函数设置唯一的名称，避免Flask端点冲突
        self.counter += 1
        wrapped.__name__ = f"rate_limited_{f.__name__}_{self.counter}"
        return wrapped

# 带有指数退避的请求函数
def request_with_backoff(url, headers, params=None, json=None, max_retries=5):
    retry_count = 0
    backoff_factor = 1  # 初始退避时间（秒）
    method = 'POST' if json else 'GET'
    
    while retry_count <= max_retries:
        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, params=params, json=json)
            else:
                response = requests.get(url, headers=headers, params=params)
            
            # 检查是否是飞书API频率限制错误（错误码99991400）
            try:
                response_data = response.json()
                if response_data.get('code') == 99991400:
                    if retry_count < max_retries:
                        # 飞书频率限制，使用更长的退避时间
                        backoff_time = backoff_factor * (3 ** retry_count) + random.uniform(1, 3)  # 更长的退避
                        app.logger.warning(f"Feishu rate limit hit (code 99991400). Retrying in {backoff_time:.2f} seconds. Retry count: {retry_count + 1}")
                        time.sleep(backoff_time)
                        retry_count += 1
                        continue
                    else:
                        # 达到最大重试次数
                        app.logger.error("Max retries reached for Feishu rate limit. Raising exception.")
                        response.raise_for_status()
            except ValueError:
                # 响应不是JSON格式，继续正常处理
                pass
            
            # 处理HTTP 429速率限制错误
            if response.status_code == 429:  # 速率限制错误
                if retry_count < max_retries:
                    # 计算退避时间
                    backoff_time = backoff_factor * (2 ** retry_count) + random.uniform(0, 1)
                    app.logger.warning(f"HTTP rate limit hit. Retrying in {backoff_time:.2f} seconds. Retry count: {retry_count + 1}")
                    time.sleep(backoff_time)
                    retry_count += 1
                    continue
                else:
                    # 达到最大重试次数
                    app.logger.error("Max retries reached for HTTP rate limit. Raising exception.")
                    response.raise_for_status()
            # 处理HTTP 401认证错误
            elif response.status_code == 401:
                # 认证失败，记录日志并抛出异常
                app.logger.error(f"Authentication failed with status code 401. URL: {url}")
                response.raise_for_status()
            else:
                response.raise_for_status()
                return response
        except requests.exceptions.RequestException as e:
            # 只有在速率限制错误时才重试，其他错误直接抛出
            if (hasattr(e, 'response') and e.response is not None and e.response.status_code == 429) or \
               (hasattr(e, 'response') and e.response is not None and 
                (lambda: (lambda r: r.json().get('code') if r else None)(e.response))() == 99991400):
                if retry_count < max_retries:
                    backoff_time = backoff_factor * (2 ** retry_count) + random.uniform(0, 1)
                    app.logger.warning(f"Rate limit error. Retrying in {backoff_time:.2f} seconds. Error: {str(e)}")
                    time.sleep(backoff_time)
                    retry_count += 1
                else:
                    app.logger.error(f"Max retries reached for rate limit error. Raising exception. Error: {str(e)}")
                    raise
            else:
                # 对于非速率限制错误，直接抛出异常，不重试
                app.logger.error(f"Non-rate limit error occurred. Not retrying. Error: {str(e)}")
                raise
    
    # 如果循环结束仍未成功，抛出异常
    raise requests.exceptions.RequestException("Max retries reached without successful response")

# 限制请求频率为 100 次/分钟，防止超频报错
rate_limiter = RateLimiter(max_calls=50, per_seconds=1)

# 获取知识空间信息接口
@app.route('/api/wiki/spaces', methods=['GET'])
@rate_limiter
def get_wiki_spaces():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Unauthorized"}), 401
    user_access_token = auth_header.split(' ')[1]

    page_token = request.args.get('page_token')
    # 限制 page_size 最大为 50，符合飞书 API 限制
    page_size = min(int(request.args.get('page_size', 50)), 50)  # 默认值改为50

    url = "https://open.feishu.cn/open-apis/wiki/v2/spaces"
    headers = {"Authorization": f"Bearer {user_access_token}"}
    params = {
        "page_size": page_size
    }
    if page_token:
        params['page_token'] = page_token

    try:
        # 使用带有指数退避的请求函数，更好地处理频率限制
        response = request_with_backoff(url, headers, params)
        return jsonify(response.json().get("data", {}))
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request error: {str(e)}")
        if e.response is not None:
            app.logger.error(f"Response status: {e.response.status_code}")
            app.logger.error(f"Response content: {e.response.text}")
            try:
                error_data = e.response.json()
                return jsonify({"error": error_data}), e.response.status_code
            except ValueError:
                return jsonify({"error": e.response.text}), e.response.status_code
        return jsonify({"error": str(e)}), 500

# --- Node Fetching Logic ---

def fetch_node_children(space_id, node_token, user_access_token, page_token=None):
    url = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/{space_id}/nodes"
    headers = {"Authorization": f"Bearer {user_access_token}"}
    params = {"page_size": 50}
    if node_token:
        params['parent_node_token'] = node_token
    if page_token:
        params['page_token'] = page_token

    @rate_limiter
    def fetch_with_rate_limit():
        # 使用带有指数退避的请求函数，更好地处理频率限制
        return request_with_backoff(url, headers, params)

    response = fetch_with_rate_limit()
    return response.json().get("data", {})



def fetch_all_nodes_recursively(space_id, user_access_token, parent_node_token=None, page_token=None, progress_callback=None):
    nodes = []
    total_count = 0  # 用于累计节点总数
    retry_count = 0  # 重试计数器
    max_retries = 3  # 最大重试次数
    
    while True:
        url = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/{space_id}/nodes?page_size=50"
        headers = {
            "Authorization": f"Bearer {user_access_token}"
        }
        params = {}
        if parent_node_token:
            params['parent_node_token'] = parent_node_token
        if page_token:
            params['page_token'] = page_token

        try:
            # 使用带有指数退避的请求函数
            response = request_with_backoff(url, headers, params)
            data = response.json().get("data", {})
            items = data.get("items", [])
            # 过滤掉缺少node_token的节点
            valid_items = [item for item in items if item.get('node_token')]
            nodes.extend(valid_items)
            
            # 重置重试计数器
            retry_count = 0
            
            # 更新总节点数并调用进度回调
            total_count += len(items)
            if progress_callback:
                try:
                    # 调用进度回调函数
                    progress_callback(total_count)
                except Exception as e:
                    # 记录错误但不中断主流程
                    app.logger.error(f"Progress callback error: {str(e)}")

            # 限制并发数为2，避免触发飞书API频率限制
            with ThreadPoolExecutor(max_workers=2) as executor:
                # 为每个子节点请求添加小延迟，避免同时发送大量请求
                futures = []
                for item in items:
                    if item.get('has_child'):
                        # 添加小延迟避免频率限制
                        time.sleep(0.1)
                        future = executor.submit(fetch_all_nodes_recursively, space_id, user_access_token, item['node_token'], None, progress_callback)
                        futures.append((future, item))
                
                for future, item in futures:
                    try:
                        children = future.result()
                        # Find the node in the list and add its children
                        for n in nodes:
                            if n['node_token'] == item['node_token']:
                                n['children'] = children
                                break
                    except Exception as exc:
                        app.logger.error(f'{item["node_token"]} generated an exception: {exc}')
                        # 继续处理其他节点，不中断整个过程
                        continue

            if not data.get('has_more'):
                break
            page_token = data.get('page_token')
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Failed to fetch nodes: {str(e)}")
            # 如果是速率限制错误，重新抛出异常以便上层处理
            if e.response is not None and e.response.status_code == 429:
                raise
            # 如果是网络错误，尝试重试
            elif isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
                if retry_count < max_retries:
                    retry_count += 1
                    # 计算退避时间
                    backoff_time = 2 ** retry_count  # 指数退避
                    app.logger.warning(f"Network error, retrying in {backoff_time} seconds (attempt {retry_count}/{max_retries})")
                    time.sleep(backoff_time)
                    continue
                else:
                    app.logger.error(f"Max retries reached for network error: {str(e)}")
                    raise
            # 对于其他错误，可以选择继续或者抛出异常
            else:
                # 如果已经获取了一些数据，继续处理而不是抛出异常
                if nodes:
                    app.logger.warning(f"Error occurred but continuing with already fetched data: {str(e)}")
                    break
                else:
                    raise
        except Exception as e:
            app.logger.error(f"Unexpected error in fetch_all_nodes_recursively: {str(e)}")
            # 如果已经获取了一些数据，继续处理而不是抛出异常
            if nodes:
                app.logger.warning(f"Unexpected error but continuing with already fetched data: {str(e)}")
                break
            else:
                raise
    return nodes

@app.route('/api/wiki/<space_id>/nodes/all', methods=['GET'])
def get_all_wiki_nodes(space_id):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Unauthorized"}), 401
    user_access_token = auth_header.split(' ')[1]

    try:
        all_nodes = fetch_all_nodes_recursively(space_id, user_access_token)
        return jsonify(all_nodes)
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request error: {str(e)}")
        if e.response is not None:
            app.logger.error(f"Response status: {e.response.status_code}")
            app.logger.error(f"Response content: {e.response.text}")
            # 特别处理速率限制错误
            if e.response.status_code == 429:
                return jsonify({"error": "Rate limit exceeded. Please try again later.", "retry_after": 60}), 429
            try:
                error_data = e.response.json()
                return jsonify({"error": error_data}), e.response.status_code
            except ValueError:
                return jsonify({"error": e.response.text}), e.response.status_code
        return jsonify({"error": str(e)}), 500

# 兼容旧版本的API端点，用于导出全量导航数据
@app.route('/api/wiki/nodes/export', methods=['GET'])
def export_wiki_nodes():
    # 从查询参数获取space_id
    space_id = request.args.get('space_id')
    if not space_id:
        return jsonify({"error": "Missing space_id parameter"}), 400
    
    # 从查询参数或Authorization头获取token
    user_access_token = request.args.get('token')
    if not user_access_token:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Unauthorized"}), 401
        user_access_token = auth_header.split(' ')[1]

    app.logger.info(f"SSE export connection attempt started for space_id: {space_id}")
    
    # 创建一个队列来传递进度更新
    import queue
    progress_queue = queue.Queue()
    result = []

    def generate():
        try:
            app.logger.info(f"SSE export stream generation started for space_id: {space_id}")
            
            # 定义进度回调函数
            def progress_callback(count):
                progress_queue.put(count)
            
            # 在另一个线程中获取所有节点
            import threading
            def fetch_nodes():
                try:
                    nonlocal result
                    app.logger.info(f"Starting to fetch all nodes for export, space_id: {space_id}")
                    all_nodes = fetch_all_nodes_recursively(space_id, user_access_token, progress_callback=progress_callback)
                    result.extend(all_nodes)
                    app.logger.info(f"Finished fetching all nodes for export, space_id: {space_id}, node count: {len(result)}")
                    # 发送完成信号
                    progress_queue.put(None)
                except Exception as e:
                    app.logger.error(f"Error while fetching nodes for export, space_id: {space_id}, error: {str(e)}")
                    # 发送错误信号
                    progress_queue.put(e)
            
            fetch_thread = threading.Thread(target=fetch_nodes)
            fetch_thread.start()
            
            # 实时发送进度更新
            while True:
                try:
                    # 从队列中获取进度更新
                    item = progress_queue.get(timeout=1)
                    
                    # 检查是否完成
                    if item is None:
                        break
                    
                    # 检查是否出错
                    if isinstance(item, Exception):
                        raise item
                    
                    # 发送进度更新
                    yield f"data: {{\"type\": \"progress\", \"count\": {item}}}\n\n"
                except queue.Empty:
                    # 检查线程是否还在运行
                    if not fetch_thread.is_alive():
                        break
                    continue
            
            # 等待线程完成
            fetch_thread.join()
            
            # 发送最终结果
            app.logger.info(f"Sending final export result for space_id: {space_id}, node count: {len(result)}")
            yield f"data: {{\"type\": \"result\", \"data\": {json.dumps(result)}}}\n\n"
            
            # 显式结束流
            app.logger.info(f"SSE export stream ended normally for space_id: {space_id}")
            yield "data: \n\n"
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Request error in export: {str(e)}")
            if e.response is not None:
                app.logger.error(f"Response status: {e.response.status_code}")
                app.logger.error(f"Response content: {e.response.text}")
                # 特别处理速率限制错误
                if e.response.status_code == 429:
                    app.logger.info(f"Rate limit exceeded for export, space_id: {space_id}")
                    yield f"data: {{\"type\": \"error\", \"message\": \"Rate limit exceeded. Please try again later.\", \"retry_after\": 60}}\n\n"
                    return
            app.logger.info(f"Sending request error for export, space_id: {space_id}")
            yield f"data: {{\"type\": \"error\", \"message\": \"{str(e)}\"}}\n\n"
            
            # 显式结束流
            app.logger.info(f"SSE export stream ended with request error for space_id: {space_id}")
            yield "data: \n\n"
        except Exception as e:
            app.logger.error(f"Unexpected error in export: {str(e)}")
            app.logger.info(f"Sending unexpected error for export, space_id: {space_id}")
            yield f"data: {{\"type\": \"error\", \"message\": \"{str(e)}\"}}\n\n"
            
            # 显式结束流
            app.logger.info(f"SSE export stream ended with unexpected error for space_id: {space_id}")
            yield "data: \n\n"
    
    app.logger.info(f"SSE export connection established for space_id: {space_id}")
    return Response(generate(), content_type='text/event-stream')

@app.route('/api/wiki/<space_id>/nodes/all/stream', methods=['GET'])
def get_all_wiki_nodes_stream(space_id):
    # 从查询参数或Authorization头获取token
    user_access_token = request.args.get('token')
    if not user_access_token:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Unauthorized"}), 401
        user_access_token = auth_header.split(' ')[1]

    app.logger.info(f"SSE connection attempt started for space_id: {space_id}")
    
    # 创建一个队列来传递进度更新
    import queue
    progress_queue = queue.Queue()
    result = []
    connection_active = True  # 连接状态标志

    def generate():
        nonlocal connection_active
        try:
            app.logger.info(f"SSE stream generation started for space_id: {space_id}")
            
            # 定义进度回调函数
            def progress_callback(count):
                if connection_active:  # 只有在连接活跃时才向队列添加数据
                    try:
                        progress_queue.put(count)
                    except Exception as e:
                        app.logger.error(f"Error adding progress to queue: {str(e)}")
            
            # 在另一个线程中获取所有节点
            import threading
            def fetch_nodes():
                try:
                    nonlocal result
                    app.logger.info(f"Starting to fetch all nodes for space_id: {space_id}")
                    all_nodes = fetch_all_nodes_recursively(space_id, user_access_token, progress_callback=progress_callback)
                    result.extend(all_nodes)
                    app.logger.info(f"Finished fetching all nodes for space_id: {space_id}, node count: {len(result)}")
                    # 发送完成信号
                    if connection_active:
                        progress_queue.put(None)
                except Exception as e:
                    app.logger.error(f"Error while fetching nodes for space_id: {space_id}, error: {str(e)}")
                    # 发送错误信号
                    if connection_active:
                        progress_queue.put(e)
            
            fetch_thread = threading.Thread(target=fetch_nodes)
            fetch_thread.start()
            
            # 实时发送进度更新
            while connection_active:
                try:
                    # 从队列中获取进度更新，使用更短的超时时间以便更快响应连接关闭
                    item = progress_queue.get(timeout=0.5)
                    
                    # 检查是否完成
                    if item is None:
                        break
                    
                    # 检查是否出错
                    if isinstance(item, Exception):
                        raise item
                    
                    # 发送进度更新
                    yield f"data: {{\"type\": \"progress\", \"count\": {item}}}\n\n"
                except queue.Empty:
                    # 检查线程是否还在运行
                    if not fetch_thread.is_alive():
                        break
                    continue
                except Exception as e:
                    app.logger.error(f"Error in stream generation loop: {str(e)}")
                    break
            
            # 等待线程完成
            fetch_thread.join(timeout=5)  # 添加超时，避免无限等待
            
            # 如果连接仍然活跃，发送最终结果
            if connection_active:
                app.logger.info(f"Sending final result for space_id: {space_id}, node count: {len(result)}")
                yield f"data: {{\"type\": \"result\", \"data\": {json.dumps(result)}}}\n\n"
                
                # 显式结束流
                app.logger.info(f"SSE stream ended normally for space_id: {space_id}")
                yield "data: \n\n"
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Request error: {str(e)}")
            if e.response is not None:
                app.logger.error(f"Response status: {e.response.status_code}")
                app.logger.error(f"Response content: {e.response.text}")
                # 特别处理速率限制错误
                if e.response.status_code == 429:
                    app.logger.info(f"Rate limit exceeded for space_id: {space_id}")
                    yield f"data: {{\"type\": \"error\", \"message\": \"Rate limit exceeded. Please try again later.\", \"retry_after\": 60}}\n\n"
                    return
            app.logger.info(f"Sending request error for space_id: {space_id}")
            yield f"data: {{\"type\": \"error\", \"message\": \"{str(e)}\"}}\n\n"
        except Exception as e:
            app.logger.error(f"Unexpected error: {str(e)}")
            app.logger.info(f"Sending unexpected error for space_id: {space_id}")
            yield f"data: {{\"type\": \"error\", \"message\": \"{str(e)}\"}}\n\n"
        finally:
            # 确保连接状态被正确标记为关闭
            connection_active = False
            app.logger.info(f"SSE stream ended for space_id: {space_id}")
    
    app.logger.info(f"SSE connection established for space_id: {space_id}")
    return Response(generate(), content_type='text/event-stream')

@app.route('/api/wiki/<space_id>/nodes', methods=['GET'])
def get_wiki_nodes(space_id):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Unauthorized"}), 401
    user_access_token = auth_header.split(' ')[1]

    # Get parameters
    parent_node_token = request.args.get('parent_node_token')
    page_token = request.args.get('page_token')
    
    # Validate parameters
    if parent_node_token is not None and not isinstance(parent_node_token, str):
        return jsonify({"error": "Invalid parent_node_token"}), 400
    if page_token is not None and not isinstance(page_token, str):
        return jsonify({"error": "Invalid page_token"}), 400

    try:
        # Fetch nodes with pagination
        data = fetch_node_children(space_id, parent_node_token, user_access_token, page_token)
        return jsonify(data)

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request error: {str(e)}")
        if e.response is not None:
            app.logger.error(f"Response status: {e.response.status_code}")
            app.logger.error(f"Response content: {e.response.text}")
            try:
                error_data = e.response.json()
                return jsonify({"error": error_data}), e.response.status_code
            except ValueError:
                return jsonify({"error": e.response.text}), e.response.status_code
        return jsonify({"error": str(e)}), 500

@app.route('/api/wiki/doc/<obj_token>', methods=['GET'])
def get_wiki_document(obj_token):
    # 记录请求信息，便于调试
    app.logger.info(f"=== Incoming /api/wiki/doc/{obj_token} Request ===")
    app.logger.info(f"Request headers: {dict(request.headers)}")
    
    # 支持多种认证方式，增强健壮性
    user_access_token = None
    auth_header = request.headers.get('Authorization')
    user_access_token_header = request.headers.get('user-access-token')
    
    # 优先使用 Authorization 头（标准Bearer Token）
    if auth_header and auth_header.startswith('Bearer '):
        user_access_token = auth_header.split(' ')[1]
        app.logger.info("Using Authorization header for authentication")
    # 兼容 user-access-token 头
    elif user_access_token_header:
        user_access_token = user_access_token_header
        app.logger.info("Using user-access-token header for authentication")
    
    # 如果没有找到任何认证信息
    if not user_access_token:
        app.logger.error("No valid authentication token found in request headers")
        app.logger.error(f"Available headers: {list(request.headers.keys())}")
        return jsonify({"error": "Authentication required. Please provide valid token in Authorization or user-access-token header"}), 401
    
    # 记录token信息（脱敏处理）
    token_preview = user_access_token[:10] + "..." if len(user_access_token) > 10 else user_access_token
    app.logger.info(f"Authentication successful, token preview: {token_preview}")
    
    url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{obj_token}/raw_content"
    headers = {
        "Authorization": f"Bearer {user_access_token}"
    }
    
    app.logger.info(f"Fetching document content from Feishu with URL: {url}")
    app.logger.info(f"Document obj_token: {obj_token}")

    try:
        response = requests.get(url, headers=headers)
        app.logger.info(f"Feishu API response status: {response.status_code}")
        app.logger.info(f"Feishu API response headers: {dict(response.headers)}")
        
        response.raise_for_status()
        data = response.json()
        app.logger.info(f"Feishu API response data: {data}")
        
        if data.get("code") == 0:
            document_data = data.get("data", {})
            content_length = len(document_data.get('content', ''))
            app.logger.info(f"Successfully fetched document content, length: {content_length}")
            return jsonify(document_data)
        else:
            error_msg = data.get("msg", "Failed to fetch document")
            app.logger.error(f"Feishu API returned error: {error_msg}")
            app.logger.error(f"Feishu API error code: {data.get('code')}")
            return jsonify({"error": error_msg}), 500
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to fetch document content: {e}"
        app.logger.error(error_msg)
        if e.response is not None:
            app.logger.error(f"Response status: {e.response.status_code}")
            app.logger.error(f"Response headers: {dict(e.response.headers)}")
            app.logger.error(f"Response content: {e.response.text}")
            try:
                error_data = e.response.json()
                return jsonify({"error": error_data}), e.response.status_code
            except ValueError:
                return jsonify({"error": e.response.text}), e.response.status_code
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    data = request.json
    api_key = data.get('api_key')
    model = data.get('model', 'doubao-seed-1-6-250615')  # 默认模型参数
    messages = data.get('messages')

    if not all([api_key, messages]):
        return jsonify({"error": "Missing required parameters"}), 400

    def generate():
        try:
            # 使用OpenAI SDK进行流式调用
            client = OpenAI(
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=api_key
            )
            
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
            )
            
            for chunk in stream:
                if not chunk.choices:
                    continue
                
                # 处理 reasoning_content
                reasoning_content = ""
                if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                    reasoning_content = chunk.choices[0].delta.reasoning_content or ""
                if reasoning_content:
                    # 按照SSE格式返回推理内容，并添加前缀以区分
                    # 使用 json.dumps 确保内容被正确转义
                    import json
                    yield f"data: {{\"type\": \"reasoning\", \"content\": {json.dumps(reasoning_content)}}}\n\n"
                
                # 处理 content
                content = ""
                if hasattr(chunk.choices[0].delta, 'content'):
                    content = chunk.choices[0].delta.content or ""
                if content:
                    # 按照SSE格式返回内容，并添加前缀以区分
                    # 使用 json.dumps 确保内容被正确转义
                    import json
                    yield f"data: {{\"type\": \"content\", \"content\": {json.dumps(content)}}}\n\n"
            
            # 发送结束信号
            yield "data: [DONE]\n\n"
        except Exception as e:
            app.logger.error(f"LLM request error: {e}")
            # 使用 json.dumps 确保错误信息被正确转义
            import json
            yield f"data: {{\"error\": {json.dumps(str(e))}}}\n\n"

    return Response(generate(), content_type='text/event-stream')


def replace_placeholders(prompt_template, placeholders):
    """
    统一的占位符替换函数
    :param prompt_template: 提示词模板
    :param placeholders: 占位符字典
    :return: 替换后的提示词
    """
    app.logger.info(f"Starting placeholder replacement with template length: {len(prompt_template) if prompt_template else 0}")
    app.logger.debug(f"Placeholders to replace: {placeholders}")
    
    if not prompt_template:
        app.logger.warning("Empty prompt_template provided to replace_placeholders")
        return prompt_template
    
    if not isinstance(placeholders, dict):
        app.logger.error(f"Invalid placeholders type: {type(placeholders)}, expected dict")
        return prompt_template
    
    result = prompt_template
    replaced_count = 0
    
    for placeholder, value in placeholders.items():
        if not isinstance(placeholder, str):
            app.logger.warning(f"Invalid placeholder type: {type(placeholder)}, skipping")
            continue
            
        placeholder_pattern = f'{{{placeholder}}}'
        if placeholder_pattern in result:
            # 确保占位符被正确替换，即使值为None也替换为空字符串
            replacement_value = str(value) if value is not None else ''
            result = result.replace(placeholder_pattern, replacement_value)
            replaced_count += 1
            app.logger.debug(f"Replaced placeholder '{placeholder}' with value (length: {len(replacement_value)})")
        else:
            app.logger.debug(f"Placeholder '{placeholder}' not found in template")
    
    # 检查是否还有未替换的占位符
    import re
    remaining_placeholders = re.findall(r'\{([^}]+)\}', result)
    if remaining_placeholders:
        app.logger.warning(f"Found unreplaced placeholders: {remaining_placeholders}")
    
    app.logger.info(f"Placeholder replacement completed: {replaced_count} placeholders replaced")
    app.logger.debug(f"Final prompt length after replacement: {len(result)}")
    return result

@app.route('/api/llm/stream_analysis', methods=['POST'])
def stream_analysis():
    data = request.json
    app.logger.info(f"Received stream_analysis request with data: {data}")
    
    api_key = data.get('api_key')
    model = data.get('model', 'doubao-seed-1-6-250615')  # 默认模型参数
    messages = data.get('messages')
    prompt_template = data.get('prompt_template')  # 获取提示词模板
    placeholders = data.get('placeholders', {})  # 获取占位符字典

    # 检查必需参数：api_key 是必须的，messages 或 (prompt_template 和 placeholders) 之一必须提供
    if not api_key:
        error_msg = "Missing api_key"
        app.logger.error(error_msg)
        return jsonify({"error": error_msg}), 400

    # 如果提供了提示词模板和占位符，则进行替换以生成 messages
    if prompt_template:
        # 合并默认占位符和传入的占位符
        all_placeholders = {}
        # 可以在这里添加一些默认的占位符
        all_placeholders.update(placeholders)
        prompt = replace_placeholders(prompt_template, all_placeholders)
        # 使用替换后的提示词
        messages = [{'role': 'user', 'content': prompt}]
        app.logger.info(f"Prompt after placeholder replacement: {prompt}")
    
    # 如果到这里还没有 messages，则报错
    if not messages:
        error_msg = "Missing messages or (prompt_template and placeholders)"
        app.logger.error(error_msg)
        return jsonify({"error": error_msg}), 400

    # 处理额外参数
    extra_params = {}
    temperature = data.get('temperature')
    max_tokens = data.get('max_tokens')

    if temperature is not None:
        extra_params['temperature'] = temperature
    if max_tokens is not None:
        extra_params['max_tokens'] = max_tokens

    def generate():
        try:
            # 使用OpenAI SDK进行流式调用
            client = OpenAI(
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=api_key
            )
            
            # 准备调用参数
            call_params = {
                "model": model,
                "messages": messages,
                "stream": True,
                **extra_params  # 展开额外参数
            }
            
            app.logger.info(f"Calling LLM with params: {call_params}")
            app.logger.info(f"Prompt sent to LLM (first 500 chars): {call_params['messages'][0]['content'][:500]}...")
            
            stream = client.chat.completions.create(**call_params)
            
            for chunk in stream:
                if not chunk.choices:
                    continue
                
                # 处理 reasoning_content
                reasoning_content = ""
                if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                    reasoning_content = chunk.choices[0].delta.reasoning_content or ""
                if reasoning_content:
                    # 按照SSE格式返回推理内容，并添加前缀以区分
                    # 使用 json.dumps 确保内容被正确转义
                    import json
                    yield f"data: {{\"type\": \"reasoning\", \"content\": {json.dumps(reasoning_content)}}}\n\n"
                
                # 处理 content
                content = ""
                if hasattr(chunk.choices[0].delta, 'content'):
                    content = chunk.choices[0].delta.content or ""
                if content:
                    # 按照SSE格式返回内容，并添加前缀以区分
                    # 使用 json.dumps 确保内容被正确转义
                    import json
                    yield f"data: {{\"type\": \"content\", \"content\": {json.dumps(content)}}}\n\n"
            
            # 发送结束信号
            yield "data: [DONE]\n\n"
        except Exception as e:
            error_msg = f"LLM Request error: {str(e)}"
            app.logger.error(error_msg)
            # 使用 json.dumps 确保错误信息被正确转义
            import json
            yield f"data: {{\"error\": {json.dumps(str(e))}}}\n\n"

    app.logger.info("Starting stream response for LLM analysis")
    return Response(generate(), content_type='text/event-stream')

@app.route('/api/llm/doc_import_analysis', methods=['POST'])
def doc_import_analysis():
    data = request.json
    app.logger.info(f"Received doc_import_analysis request with data: {data}")
    
    doc_token = data.get('doc_token')
    doc_type = data.get('doc_type', 'docx')  # 获取文档类型，默认为docx
    wiki_node_md = data.get('wiki_node_md')
    api_key = data.get('api_key')
    model = data.get('model', 'doubao-seed-1-6-250615')  # 从请求参数获取模型名称，使用新的默认值
    max_tokens = data.get('max_tokens')  # 获取最大输出令牌数
    prompt_template = data.get('prompt_template')  # 从请求参数获取提示词模板
    wiki_title = data.get('wiki_title')  # 从请求参数获取知识库标题
    placeholders = data.get('placeholders', {})  # 获取占位符字典
    user_access_token = request.headers.get('Authorization')
    if user_access_token:
        user_access_token = user_access_token.replace('Bearer ', '')

    if not all([doc_token, wiki_node_md, api_key, user_access_token]):
        error_msg = "Missing required parameters"
        app.logger.error(error_msg)
        return jsonify({"error": error_msg}), 400

    # 1. Get document content from Feishu
    doc_content = ''
    try:
        # 如果是wiki类型，需要先获取实际的obj_type和obj_token
        if doc_type == 'wiki':
            app.logger.info(f"Processing wiki type document with token: {doc_token}")
            # 调用获取知识空间节点接口
            node_url = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token={doc_token}"
            headers = {"Authorization": f"Bearer {user_access_token}"}
            app.logger.info(f"Fetching wiki node info with URL: {node_url}")
            
            node_response = requests.get(node_url, headers=headers)
            node_response.raise_for_status()
            node_data = node_response.json()
            app.logger.info(f"Received wiki node info: {node_data}")
            
            if node_data.get("code") == 0:
                node_info = node_data.get("data", {})
                # 从嵌套的node对象中获取obj_type和obj_token
                node_detail = node_info.get("node", {})
                actual_obj_type = node_detail.get("obj_type")
                actual_obj_token = node_detail.get("obj_token")
                
                # 添加详细的调试日志，记录完整的数据结构
                app.logger.info(f"Wiki node data structure - node_info: {node_info}")
                app.logger.info(f"Wiki node detail - node_detail: {node_detail}")
                app.logger.info(f"Wiki node resolved - obj_type: {actual_obj_type}, obj_token: {actual_obj_token}")
                
                # 配置化的支持文档类型，便于扩展
                SUPPORTED_DOC_TYPES = ['doc', 'docx']
                
                # 检查obj_type是否为支持的文档类型
                if not actual_obj_type:
                    error_msg = f"Failed to extract document type from wiki node. Response structure may have changed."
                    app.logger.error(error_msg)
                    app.logger.error(f"Available fields in node_detail: {list(node_detail.keys()) if node_detail else 'None'}")
                    return jsonify({"error": error_msg}), 400
                
                # 检查obj_token是否存在
                if not actual_obj_token:
                    error_msg = f"Failed to extract document token from wiki node. Document token is required."
                    app.logger.error(error_msg)
                    app.logger.error(f"Document type: {actual_obj_type}, Available fields: {list(node_detail.keys()) if node_detail else 'None'}")
                    return jsonify({"error": error_msg}), 400
                
                if actual_obj_type not in SUPPORTED_DOC_TYPES:
                    error_msg = f"Unsupported document type: {actual_obj_type}. Only {', '.join(SUPPORTED_DOC_TYPES)} types are supported."
                    app.logger.error(error_msg)
                    app.logger.error(f"Document token: {actual_obj_token}, Available types: {list(node_detail.keys()) if node_detail else 'None'}")
                    return jsonify({"error": error_msg}), 400
                
                # 根据文档类型构建不同的API URL，增强可扩展性
                if actual_obj_type == 'docx':
                    doc_url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{actual_obj_token}/raw_content"
                elif actual_obj_type == 'doc':
                    doc_url = f"https://open.feishu.cn/open-apis/doc/v1/documents/{actual_obj_token}/raw_content"
                else:
                    # 理论上不会执行到这里，因为前面已经检查了支持的类型
                    error_msg = f"Document type {actual_obj_type} not implemented yet."
                    app.logger.error(error_msg)
                    return jsonify({"error": error_msg}), 500
                app.logger.info(f"Fetching document content for wiki with resolved URL: {doc_url}")
            else:
                error_msg = node_data.get("msg", "Failed to fetch wiki node info")
                app.logger.error(error_msg)
                return jsonify({"error": error_msg}), 500
        else:
            # 直接使用doc_token获取文档内容
            doc_url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_token}/raw_content"
            app.logger.info(f"Fetching document content from Feishu with URL: {doc_url}")
        
        # 获取文档内容
        headers = {"Authorization": f"Bearer {user_access_token}"}
        response = requests.get(doc_url, headers=headers)
        response.raise_for_status()
        doc_data = response.json()
        app.logger.info(f"Received response from Feishu: {doc_data}")
        
        if doc_data.get("code") == 0:
            doc_content = doc_data.get("data", {}).get('content', '')
            app.logger.info(f"Successfully fetched document content, length: {len(doc_content)}")
        else:
            error_msg = doc_data.get("msg", "Failed to fetch document content")
            app.logger.error(error_msg)
            return jsonify({"error": error_msg}), 500
            
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to fetch document content: {e}"
        app.logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

    # 2. Construct prompt and call LLM
    # 如果提供了提示词模板，则使用模板替换占位符，否则使用默认提示词
    # 优化占位符命名以提高可维护性
    if prompt_template:
        # 合并默认占位符和传入的占位符
        all_placeholders = {
            'IMPORTED_DOCUMENT_CONTENT': doc_content,
            'KNOWLEDGE_BASE_STRUCTURE': wiki_node_md,
            'WIKI_TITLE': wiki_title or ''
        }
        all_placeholders.update(placeholders)
        prompt = replace_placeholders(prompt_template, all_placeholders)
        # 记录占位符替换前后的对比，便于调试
        app.logger.info(f"Placeholder replacement debug:")
        app.logger.info(f"  - IMPORTED_DOCUMENT_CONTENT length: {len(doc_content)}")
        app.logger.info(f"  - KNOWLEDGE_BASE_STRUCTURE length: {len(wiki_node_md)}")
        app.logger.info(f"  - WIKI_TITLE: {wiki_title}")
        app.logger.info(f"  - Received placeholders: {placeholders}")
        app.logger.info(f"Prompt after placeholder replacement (first 200 chars): {prompt[:200]}...")
    else:
        prompt = f"""你是一位专业的知识管理专家，具备以下能力：
1. 深入理解文档内容，分析其主题、关键信息和潜在价值。
2. 熟悉知识库的现有结构，能够准确判断文档的最佳归属节点。
3. 提供清晰、有说服力的分析和建议，帮助用户做出决策。

## 评估材料
**知识库标题**：
{wiki_title or ''}

**导入文档内容**：
{doc_content}

**当前知识库结构**：
{wiki_node_md}

## 评估任务
请根据以上材料，完成以下三个任务：

### 1. 内容匹配度分析
分析导入文档与知识库现有节点的相关性，评估其在知识库中的潜在价值。

### 2. 归属节点建议
基于内容分析，推荐1-3个最适合的现有节点作为文档的归属位置，并简要说明理由。

### 3. 导入决策
综合以上分析，给出是否建议导入该文档的最终决策（建议导入/暂不建议导入），并提供简要说明。"""
        app.logger.info(f"Using default prompt template")

    def generate():
        try:
            # 使用OpenAI SDK进行流式调用
            client = OpenAI(
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=api_key
            )
            
            # 处理额外参数
            extra_params = {}
            if max_tokens is not None:
                extra_params['max_tokens'] = max_tokens
            
            call_params = {
                "model": model,
                "messages": [{'role': 'user', 'content': prompt}],
                "stream": True,
                **extra_params  # 展开额外参数
            }
            app.logger.info(f"Calling LLM with params: {call_params}")
            
            stream = client.chat.completions.create(**call_params)
            
            for chunk in stream:
                if not chunk.choices:
                    continue
                
                # 处理 reasoning_content
                reasoning_content = ""
                if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                    reasoning_content = chunk.choices[0].delta.reasoning_content or ""
                if reasoning_content:
                    # 按照SSE格式返回推理内容，并添加前缀以区分
                    # 使用 json.dumps 确保内容被正确转义
                    import json
                    yield f"data: {{\"type\": \"reasoning\", \"content\": {json.dumps(reasoning_content)}}}\n\n"
                
                # 处理 content
                content = ""
                if hasattr(chunk.choices[0].delta, 'content'):
                    content = chunk.choices[0].delta.content or ""
                if content:
                    # 按照SSE格式返回内容，并添加前缀以区分
                    # 使用 json.dumps 确保内容被正确转义
                    import json
                    yield f"data: {{\"type\": \"content\", \"content\": {json.dumps(content)}}}\n\n"
            
            # 发送结束信号
            yield "data: [DONE]\n\n"
        except Exception as e:
            error_msg = f"LLM Request error: {str(e)}"
            app.logger.error(error_msg)
            # 使用 json.dumps 确保错误信息被正确转义
            import json
            yield f"data: {{\"error\": {json.dumps(str(e))}}}\n\n"
        finally:
            app.logger.info("Finished stream response for document import analysis")

    app.logger.info("Starting stream response for document import analysis")
    return Response(generate(), content_type='text/event-stream')

@app.route('/api/wiki/search', methods=['GET', 'POST'])
def search_wiki():
    """飞书Wiki搜索API端点 - 优化版搜索逻辑"""
    app.logger.info("=== Received /api/wiki/search request ===")
    
    # 验证认证
    # 优先从URL参数获取令牌，如果没有则从请求头获取
    user_access_token = request.args.get('token')
    if not user_access_token:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            app.logger.error("Missing or invalid Authorization header")
            return jsonify({"error": "Unauthorized"}), 401
        user_access_token = auth_header.split(' ')[1]
    
    app.logger.info(f"Authentication successful, token preview: {user_access_token[:10]}...")
    
    # 获取请求参数
    if request.method == 'POST':
        # POST方法：从JSON body获取参数
        try:
            request_data = request.get_json()
            app.logger.info(f"POST request data: {request_data}")
        except Exception as e:
            app.logger.error(f"Failed to parse request JSON: {str(e)}")
            return jsonify({"error": "Invalid JSON format"}), 400
        
        query = request_data.get('query')
        space_id = request_data.get('space_id')
        node_id = request_data.get('node_id')
        page_token = request_data.get('page_token')
        page_size = min(int(request_data.get('page_size', 50)), 50)  # 默认值改为50
    else:
        # GET方法：从URL参数获取
        query = request.args.get('query')
        space_id = request.args.get('space_id')
        node_id = request.args.get('node_id')
        page_token = request.args.get('page_token')
        page_size = min(int(request.args.get('page_size', 50)), 50)  # 默认值改为50
    
    # 验证必需参数
    if not query or not query.strip():
        app.logger.error("Missing or empty query parameter")
        return jsonify({"error": "Query parameter is required and cannot be empty"}), 400
      
    app.logger.info(f"Search parameters - query: {query}, space_id: {space_id}, node_id: {node_id}, page_size: {page_size}")
    
    # 构建请求参数
    search_params = {
        "page_size": page_size
    }
    if page_token:
        search_params['page_token'] = page_token
    
    # 构建请求体
    request_body = {
        "query": query.strip()
    }
    # 如果提供了space_id和node_id，添加到请求体中
    if space_id:
        request_body['space_id'] = space_id
    if node_id:
        request_body['node_id'] = node_id
    
    # 记录完整的请求信息
    app.logger.info("=== Feishu Wiki Search Request ===")
    app.logger.info(f"URL: https://open.feishu.cn/open-apis/wiki/v2/nodes/search")
    app.logger.info(f"Headers: {{\"Authorization\": \"Bearer {user_access_token[:10]}...\", \"Content-Type\": \"application/json\"}}")
    app.logger.info(f"Params: {search_params}")
    app.logger.info(f"Body: {request_body}")
    app.logger.info("="*60)
    
    try:
        # 调用飞书Wiki搜索API
        url = "https://open.feishu.cn/open-apis/wiki/v2/nodes/search"
        headers = {
            "Authorization": f"Bearer {user_access_token}",
            "Content-Type": "application/json"
        }
        
        # 使用带有指数退避的请求函数，更好地处理频率限制
        response = request_with_backoff(url, headers, search_params, json=request_body)
        
        # 记录响应信息
        app.logger.info("=== Received response from Feishu Wiki Search ===")
        app.logger.info(f"Status Code: {response.status_code}")
        app.logger.info(f"Response Content: {response.text}")
        
        response.raise_for_status()
        response_data = response.json()
        
        # 验证响应格式
        if response_data.get("code") == 0:
            # 使用流式响应，持续加载分页结果并去重
            def generate():
                # 获取初始响应数据
                nonlocal response_data
                search_result_data = response_data.get("data", {})
                initial_items = search_result_data.get("items", [])
                initial_has_more = search_result_data.get("has_more", False)
                initial_page_token = search_result_data.get("page_token")
                
                all_unique_space_ids = set()  # 记录所有已处理的space_id
                total_fetched_count = 0  # 总共获取到的知识空间详情数
                current_page_token = initial_page_token  # 当前分页令牌
                current_has_more = initial_has_more  # 是否还有更多分页
                
                # 发送初始响应
                initial_response = {
                    "type": "initial",
                    "total_unique_spaces": len(all_unique_space_ids),
                    "has_more": current_has_more,
                    "page_token": current_page_token
                }
                yield f"data: {json.dumps(initial_response)}\n\n"
                
                # 持续加载分页结果
                while True:
                    # 处理当前分页的结果
                    search_result_data = response_data.get("data", {})
                    items = search_result_data.get("items", [])
                    current_has_more = search_result_data.get("has_more", False)
                    current_page_token = search_result_data.get("page_token")
                    
                    app.logger.info(f"Processing page - found {len(items)} results, has_more: {current_has_more}")
                    
                    # 对space_id进行去重
                    space_items = []
                    for item in items:
                        space_id = item.get('space_id')
                        if space_id and space_id not in all_unique_space_ids:
                            all_unique_space_ids.add(space_id)
                            space_items.append({
                                'space_id': space_id,
                                'title': item.get('space_name', ''),  # 使用搜索结果中的space_name
                                'description': item.get('summary', '')  # 使用搜索结果中的summary作为描述
                            })
                    
                    app.logger.info(f"Found {len(space_items)} new unique spaces in current page, total unique: {len(all_unique_space_ids)}")
                    
                    # 获取当前分页中所有唯一space_id的详细信息
                    for space_item in space_items:
                        space_id = space_item['space_id']
                        try:
                            # 调用知识空间信息接口
                            space_url = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/{space_id}"
                            space_headers = {"Authorization": f"Bearer {user_access_token}"}
                            
                            # 使用带有指数退避的请求函数，更好地处理频率限制
                            space_response = request_with_backoff(space_url, space_headers)
                            space_data = space_response.json()
                            
                            if space_data.get("code") == 0:
                                space_info = space_data.get("data", {}).get("space", {})
                                # 构建返回的知识空间信息
                                space_detail = {
                                    'space_id': space_id,
                                    'title': space_info.get('name', space_item['title']),  # 优先使用API返回的名称
                                    'description': space_info.get('description', space_item['description']),  # 优先使用API返回的描述
                                    'icon': space_info.get('icon', ''),
                                    'created_time': space_info.get('create_time', 0),
                                    'updated_time': space_info.get('update_time', 0),
                                    'is_starred': space_info.get('is_starred', False),
                                    'obj_token': space_info.get('obj_token', ''),
                                    'url': space_info.get('url', '')
                                }
                                total_fetched_count += 1
                                
                                # 发送单个空间详情
                                detail_response = {
                                    "type": "detail",
                                    "item": space_detail,
                                    "fetched_count": total_fetched_count
                                }
                                yield f"data: {json.dumps(detail_response)}\n\n"
                                
                                app.logger.info(f"Successfully fetched details for space {space_id}")
                            else:
                                # 如果获取详细信息失败，跳过此知识空间
                                app.logger.warning(f"Failed to fetch details for space {space_id}, skipping this space")
                                
                        except requests.exceptions.RequestException as e:
                            # 记录错误信息
                            app.logger.error(f"Error fetching space details for {space_id}: {str(e)}")
                            # 跳过失败的知识空间
                            continue
                    
                    # 如果没有更多分页，结束循环
                    if not current_has_more:
                        break
                    
                    # 如果有更多分页，继续获取下一页
                    if current_page_token:
                        # 构建下一页的请求参数
                        next_search_params = {
                            "page_size": page_size,
                            "page_token": current_page_token
                        }
                        
                        # 构建下一页的请求体
                        next_request_body = {
                            "query": query.strip()
                        }
                        # 如果提供了space_id和node_id，添加到请求体中
                        if space_id:
                            next_request_body['space_id'] = space_id
                        if node_id:
                            next_request_body['node_id'] = node_id
                        
                        # 调用飞书Wiki搜索API获取下一页
                        next_response = request_with_backoff(url, headers, next_search_params, json=next_request_body)
                        next_response.raise_for_status()
                        next_response_data = next_response.json()
                        
                        # 验证响应格式
                        if next_response_data.get("code") != 0:
                            app.logger.error(f"Feishu search API error on next page - code: {next_response_data.get('code', -1)}, message: {next_response_data.get('msg', 'Unknown error')}")
                            break
                        
                        # 更新response_data为下一页的数据
                        response_data = next_response_data
                    else:
                        # 没有page_token但has_more为True，这是异常情况
                        app.logger.warning("has_more is True but no page_token provided")
                        break
                
                # 发送完成响应
                final_response = {
                    "type": "complete",
                    "fetched_count": total_fetched_count
                }
                yield f"data: {json.dumps(final_response)}\n\n"
                yield "data: [DONE]\n\n"
            
            return Response(generate(), content_type='text/event-stream')
        else:
            error_msg = response_data.get("msg", "Search failed")
            error_code = response_data.get("code", -1)
            app.logger.error(f"Feishu search API error - code: {error_code}, message: {error_msg}")
            return jsonify({
                "error": error_msg,
                "code": error_code
            }), 500
            
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request error during wiki search: {str(e)}")
        if e.response is not None:
            app.logger.error(f"Response status: {e.response.status_code}")
            app.logger.error(f"Response content: {e.response.text}")
            
            # 特别处理速率限制错误
            if e.response.status_code == 429:
                retry_after = e.response.headers.get('Retry-After', 60)
                return jsonify({
                    "error": "Rate limit exceeded. Please try again later.",
                    "retry_after": int(retry_after)
                }), 429
            
            try:
                error_data = e.response.json()
                return jsonify({"error": error_data}), e.response.status_code
            except ValueError:
                return jsonify({"error": e.response.text}), e.response.status_code
        
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error during wiki search: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

# 获取搜索结果的增量更新接口
@app.route('/api/wiki/search/updates/<search_id>', methods=['GET'])
@rate_limiter
def get_search_updates(search_id):
    """获取指定搜索ID的增量结果更新"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Unauthorized"}), 401
    
    # 检查搜索ID是否存在
    if not hasattr(app, 'search_threads') or search_id not in app.search_threads:
        return jsonify({"error": "Search ID not found"}), 404
    
    search_info = app.search_threads[search_id]
    thread = search_info['thread']
    
    # 检查线程是否已完成
    if thread.is_alive():
        return jsonify({
            "search_id": search_id,
            "status": "processing",
            "items": [],
            "has_more": True
        })
    else:
        # 线程已完成，返回完成状态
        # 注意：由于当前实现限制，我们无法直接获取线程的处理结果
        # 在实际应用中，应该使用共享内存或数据库来存储增量结果
        return jsonify({
            "search_id": search_id,
            "status": "completed",
            "items": [],
            "has_more": False,
            "message": "All results have been processed"
        })

# 查询搜索进度接口
@app.route('/api/wiki/search/progress/<search_id>', methods=['GET'])
@rate_limiter
def get_search_progress(search_id):
    """获取指定搜索ID的进度和额外结果"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Unauthorized"}), 401
    
    # 检查搜索ID是否存在
    if not hasattr(app, 'search_threads') or search_id not in app.search_threads:
        return jsonify({"error": "Search ID not found"}), 404
    
    search_info = app.search_threads[search_id]
    thread = search_info['thread']
    
    # 检查线程是否还在运行
    if thread.is_alive():
        # 线程还在运行，返回进度信息
        import time
        elapsed_time = time.time() - search_info['start_time']
        
        return jsonify({
            "search_id": search_id,
            "status": "processing",
            "total_spaces": search_info['total_spaces'],
            "initial_count": search_info['initial_count'],
            "elapsed_time": elapsed_time,
            "message": "Still processing additional spaces..."
        })
    else:
        # 线程已完成，尝试获取结果
        try:
            # 等待线程完成并获取结果
            thread.join(timeout=1.0)
            
            # 获取线程的返回值（如果有）
            if hasattr(thread, '_target') and hasattr(thread._target, '__self__'):
                # 这种方式不太可靠，最好使用其他方式存储结果
                pass
            
            # 由于线程函数没有直接返回结果，我们需要其他方式获取
            # 这里返回完成状态
            return jsonify({
                "search_id": search_id,
                "status": "completed",
                "total_spaces": search_info['total_spaces'],
                "initial_count": search_info['initial_count'],
                "message": "Search processing completed"
            })
        except Exception as e:
            app.logger.error(f"Error getting search progress for {search_id}: {str(e)}")
            return jsonify({"error": "Failed to get search progress"}), 500

if __name__ == '__main__':
    load_dotenv()
    
    # 打印环境变量和配置信息
    print("=== 后端应用启动配置信息 ===")
    print(f"后端端口: {BACKEND_PORT}")
    print(f"前端端口: {FRONTEND_PORT}")
    print(f"主机名: {os.getenv('HOSTNAME', 'localhost')}")
    print(f"飞书应用ID: {FEISHU_APP_ID}")
    print(f"日志级别: {os.getenv('LOG_LEVEL', 'INFO')}")
    print(f"Flask环境: {os.getenv('FLASK_ENV', 'development')}")
    print(f"CORS配置: 已启用CORS支持")
    print("==============================\n")
    
    app.run(host='0.0.0.0', port=BACKEND_PORT, debug=False, use_reloader=False)