# AI-Job-Hunter 后端基础

此目录包含 AI-Job-Hunter 黑客松 MVP 的第一版最小化 FastAPI 基础。

当前实现通过稳定的接口调用确定性模拟代理。后续可将模拟代理替换为 MiMo 驱动的代理，而无需更改 API 契约。

## 运行

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn backend.app.main:app --reload
```

打开 `http://127.0.0.1:8000/docs`。

## API 说明

`POST /api/v1/job-fit` 接收一份学生档案和一个目标岗位，并返回来源检查、匹配报告、简历建议、面试问题、警告信息和执行日志。

## 测试

```powershell
$env:PYTHONPATH = "."
python -m unittest discover -s backend/tests -v
```

## 后续计划

1. 添加真实岗位测试数据和来源验证。
2. 将三个模拟代理替换为 MiMo 客户端。
3. 持久化请求、报告、来源快照和失败信息。
4. 添加 React 工作台界面。
