# AI Service Lab

一个面向 AI 应用后端与 Agent Runtime 的工程实验仓库。

项目从 Python 异步服务出发，逐步实现模型 Provider、工具执行 Runtime 和 Agent Loop。重点不是堆叠框架，而是理解模型调用链，并通过正常路径、失败路径和自动化测试验证每一层的职责与边界。

## 当前能力

- `asyncio` 并发、超时、取消、重试、背压与优雅关闭
- FastAPI 请求校验、依赖注入、异常处理、中间件与生命周期
- OpenAI-compatible Provider 请求组装与响应解析
- 统一的 `ModelRequest`、`ModelResponse`、`ToolCall` 和 Token usage
- Provider 网络、HTTP、JSON 与协议错误分层
- Tool Runtime 参数校验、权限、超时、取消与并发执行
- Mock Agent Loop 消息回填、多工具调用与结果完整性检查
- 基于 `httpx.MockTransport` 和 pytest 的确定性测试

## 架构

```text
Client
  ↓
FastAPI
  ↓
Agent Loop
  ├──→ Model Provider ──→ OpenAI-compatible Model API
  └──→ Tool Runtime ────→ Registered Tools
```

模块职责：

```text
FastAPI
→ HTTP 接入、输入校验、请求上下文和错误响应

Model Provider
→ 供应商请求组装、HTTP 调用、响应解析和错误转换

Agent Loop
→ 维护消息历史、推进模型与工具调用、控制任务终止

Tool Runtime
→ 工具白名单、参数校验、权限、超时、取消和执行
```

## 项目结构

```text
src/ai_service/
├── app.py             # FastAPI 服务与请求生命周期实验
├── async_basics.py    # asyncio 可靠性与并发控制实验
├── config.py          # 环境变量配置与启动校验
├── providers.py       # 模型 Provider 与统一内部协议
├── tools.py           # Tool Runtime 与工具注册表
└── agent_loop.py      # Mock Agent Loop 与消息执行轨迹

tests/
├── test_async_basics.py
└── test_providers.py
```

## 环境

- Python 3.14
- Windows 为当前开发环境

安装当前实验所需依赖：

```powershell
E:\python\python3.14.0\python.exe -m pip install fastapi uvicorn httpx pydantic pydantic-settings pytest
```

## 运行验证

运行全部自动化测试：

```powershell
E:\python\python3.14.0\python.exe -m pytest -v
```

当前测试基线：

```text
20 passed
```

运行 Mock Agent Loop：

```powershell
E:\python\python3.14.0\python.exe -m src.ai_service.agent_loop
```

该实验会输出一次完整轨迹：

```text
system
→ user
→ assistant(tool_calls)
→ tool(result)
→ assistant(final)
```

## Provider 测试范围

正常路径：

- 普通文本、结束原因和 Token usage
- 工具调用 ID、工具名称和参数解析

失败路径：

- 请求超时与连接失败
- HTTP 401、429、503
- 非法 JSON、缺失或空 `choices`
- 非法 `tool_calls` 结构
- 缺失工具调用 ID 或工具名称
- 工具参数不是合法 JSON 对象

## 当前状态

Provider 已完成非流式 OpenAI-compatible 协议的 Mock 正常与失败闭环。Tool Runtime 和 Mock Agent Loop 也已分别完成最小实现。

`providers.py` 已升级为基于 `ModelRequest`、`ModelResponse` 和 `ToolCall` 的统一对象协议；`app.py`、`agent_loop.py` 与 `tools.py` 仍保留旧字典接口，当前正在进行接口统一。因此 FastAPI 入口暂不作为当前版本的运行入口。

## 下一步

```text
统一 Provider、Agent Loop 与 Tool Runtime 的内部接口
→ 完成 Function Calling 二次模型调用闭环
→ 接入真实模型 API
→ Structured Output 与 Prompt 工程
→ SSE 流式输出、客户端断开与 Token/成本统计
→ Context Engineering、RAG 与 Agent 状态管理
```

## 项目原则

- 先用 Mock 建立确定性实验，再接入真实模型
- 先理解原始协议和运行机制，再引入 Agent 框架
- 不以“成功运行一次”作为完成标准
- 每个核心模块都验证正常、异常、超时和边界路径
- 对尚未实现的能力保持明确，不把规划包装成成果
