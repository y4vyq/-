import yaml
import requests
from flask import Flask, request, Response, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
import logging

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def load_config():
    try:
        with open('config.yml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        logger.error("配置文件未找到")
        exit(1)
    except yaml.YAMLError as exc:
        logger.error(f"配置文件解析错误: {exc}")
        exit(1)

config = load_config()
PROXY_VERSION_2 = config.get('proxy_version_2', False)
FORWARDING_PORT = config.get('Forwarding_port', 8080)
TARGET_URL = f'http://localhost:{FORWARDING_PORT}'

@app.before_request
def before_request():
    if PROXY_VERSION_2:
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            client_ip = forwarded_for.split(',')[0]
            logger.info(f"客户端真实IP: {client_ip}")

def forward_request(method, url, headers, data=None, params=None):
    try:
        # 根据传入的请求数据格式，设置合适的请求体
        if isinstance(data, dict):
            data = requests.models.json.dumps(data)  # 转换为 JSON 字符串，确保 Content-Type 为 application/json
            headers['Content-Type'] = 'application/json'
        
        # 使用 requests.request 支持所有请求方法
        response = requests.request(method, url, headers=headers, data=data, params=params)
        return Response(response.content, status=response.status_code, headers=dict(response.headers))
    except requests.RequestException as e:
        logger.error(f"请求转发失败: {e}")
        return Response("请求转发失败", status=502)

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy(path):
    url = f'{TARGET_URL}/{path}'
    data = None
    files = None
    
    # 处理 POST 和 PUT 请求，特别是 multipart/form-data
    if request.method in ['POST', 'PUT']:
        content_type = request.content_type
        if 'multipart/form-data' in content_type:
            # 获取上传的文件数据
            files = request.files.to_dict()
            data = request.form.to_dict()  # 获取其他表单数据
        elif 'application/json' in content_type:
            data = request.get_json()  # 获取 JSON 数据
        elif 'application/x-www-form-urlencoded' in content_type:
            data = request.form.to_dict()  # 获取表单数据
        else:
            data = request.data  # 获取原始数据
    
    # 获取并过滤请求头（去除 Host）
    headers = {key: value for key, value in request.headers if key != 'Host'}
    
    # 日志记录请求信息
    logger.info(f"接收到请求: {request.method} {request.url}, 请求头: {dict(request.headers)}, 请求体: {data}")
    
    # 转发请求
    return forward_request(request.method, url, headers, data, params=request.args, files=files)

def forward_request(method, url, headers, data=None, params=None, files=None):
    try:
        # 如果有文件，使用 files 参数发送文件
        if files:
            response = requests.request(
                method, url, headers=headers, data=data, params=params, files=files
            )
        else:
            # 否则，发送普通请求
            response = requests.request(method, url, headers=headers, data=data, params=params)
        
        return Response(response.content, status=response.status_code, headers=dict(response.headers))
    except requests.RequestException as e:
        logger.error(f"请求转发失败: {e}")
        return Response("请求转发失败", status=502)


if __name__ == '__main__':
    app.wsgi_app = ProxyFix(app.wsgi_app)
    app.run(host='0.0.0.0', port=5000)
