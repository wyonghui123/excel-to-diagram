# Python 缓存问题解决方案

## 问题现象

修改 Python 代码后，运行结果不变，必须手动重启服务器才能生效。

## 根本原因

Python 会编译 `.py` 文件为 `.pyc` 字节码缓存到 `__pycache__` 目录。
Flask 默认不会自动检测代码变化并重载。

---

## 解决方案（已实施）

### 方案 1: Flask 热重载（推荐）✅ 已配置

**文件**: `meta/server.py`

```python
app.run(
    host='0.0.0.0', 
    port=port, 
    debug=True,          # 开启调试模式
    use_reloader=True,   # 关键：代码变化自动重启
    reloader_interval=1  # 每秒检测一次
)
```

**效果**: 修改任何 Python 文件，Flask 自动重启，无需手动操作。

### 方案 2: 开发启动脚本 ✅ 已创建

**文件**: `dev.py`（项目根目录）

```bash
# 使用方式
python dev.py
```

**功能**:
- 启动前自动清理 `__pycache__`
- 自动设置 `FLASK_DEBUG=True`
- 启用热重载

### 方案 3: NPM 脚本 ✅ 已添加

```bash
# 正常启动（带热重载）
npm run dev:python

# 强制清理缓存后启动
npm run dev:python:clean
```

---

## 最佳实践

### 1. 开发环境配置

在 `.env` 文件中添加：

```env
FLASK_DEBUG=True
PYTHONUNBUFFERED=1
```

### 2. VSCode 配置

创建 `.vscode/settings.json`:

```json
{
  "files.watcherExclude": {
    "**/__pycache__": true,
    "**/*.pyc": true
  },
  "files.exclude": {
    "**/__pycache__": true
  },
  "search.exclude": {
    "**/__pycache__": true
  }
}
```

### 3. Git Hooks（可选）

创建 `.git/hooks/pre-commit`:

```bash
#!/bin/sh
# 提交前清理缓存
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
echo "Python cache cleaned"
```

### 4. 测试脚本模板

```python
# test_xxx.py 开头添加
import sys
import os

# 确保使用最新代码
if '--no-cache' in sys.argv:
    import shutil, glob
    for d in glob.glob('**/__pycache__', recursive=True):
        shutil.rmtree(d, ignore_errors=True)
    print("[Test] Cache cleared")
```

---

## 常见问题排查

### Q: 修改代码后仍无效果？

1. 检查是否使用 `python dev.py` 或 `npm run dev:python` 启动
2. 查看终端是否有 `* Restarting with stat` 日志
3. 如果没有，手动按 `Ctrl+C` 重启

### Q: 导入错误 `ModuleNotFoundError`？

```bash
# 清理缓存后重试
npm run dev:python:clean
```

### Q: 如何确认使用的是最新代码？

```python
# 在代码中添加调试信息
import inspect
print(f"[DEBUG] File: {inspect.getfile(__name__)}")
print(f"[DEBUG] Modified: {os.path.getmtime(__file__)}")
```

---

## 相关文档

- [Flask Debug Mode](https://flask.palletsprojects.com/debug/)
- [Python Cache](https://docs.python.org/3/library/py_compile.html)
