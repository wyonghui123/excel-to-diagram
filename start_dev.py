"""启动后端服务并强制重新加载 YAML 文件"""
import os
os.environ['FLASK_DEBUG'] = 'True'

from meta.core.models import MetaRegistry

# 强制重新加载
MetaRegistry.__force_reload__ = True
print("MetaRegistry.__force_reload__ = True")

# 导入并启动
import meta.server as server_module
server_module.app = server_module.create_app()

port = int(os.environ.get('FLASK_PORT', 5000))
print("[Startup] Starting Flask on port %d" % port)
server_module.app.run(
    host='0.0.0.0',
    port=port,
    debug=True,
    use_reloader=False
)
