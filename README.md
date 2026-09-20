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
- Agent Loop 消息回填、多工具调用、二次模型调用与结果完整性检查
- Provider、Agent Loop、Tool Runtime 的统一 `ToolCall` 对象协议
- assistant 工具调用历史向 OpenAI-compatible 协议的反向序列化
- Provider → Agent Loop → Tool Runtime 的跨模块 Function Calling 集成测试
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
├── test_providers.py
├── test_tools.py
└── test_agent_loop.py
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
29 passed
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

## 测试范围

### Provider

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

### Tool Runtime

- 工具正常执行和结果序列化
- 参数类型错误与未知工具
- 未认证调用
- 工具执行超时
- 工具业务异常
- 多工具调用的 ID 保留

### 三层集成

- Agent Loop 使用真实 `OpenAICompatibleProvider` 接口
- 第一次模型响应解析为多个 `ToolCall`
- Tool Runtime 执行并回填全部工具结果
- 第二次请求包含完整的 `assistant.tool_calls`
- `assistant.tool_calls[].id` 与 `tool.tool_call_id` 集合一致
- 第二次模型调用返回最终回答

## 当前状态

Provider 已完成非流式 OpenAI-compatible 协议的 Mock 正常与失败闭环。Agent Loop 和 Tool Runtime 已统一使用 `ModelRequest`、`ModelResponse` 与 `ToolCall`，并通过两轮模型调用集成测试。

当前能够确定性验证：

```text
Agent Loop
→ OpenAICompatibleProvider
→ 模型 tool_calls
→ Tool Runtime
→ assistant/tool 消息回填
→ 第二次模型调用
→ 最终回答
```

`app.py` 仍保留早期 FastAPI 接口和旧 Provider 符号，暂未接入最新三层对象协议，因此 FastAPI 入口不是当前 Agent Runtime 的正式运行入口。

Structured Output 已完成原理、分层边界、JSON Schema、本地 Pydantic 校验和失败策略学习，但 `response_schema` 尚未写入 `ModelRequest` 和 Provider，不能视为已实现功能。

## 下一步

```text
实现 Structured Output 的 response_schema 请求与本地校验
→ 补充 Structured Output 正常和失败测试
→ 接入真实模型 API
→ SSE 流式输出、客户端断开与 Token/成本统计
→ Context Engineering、RAG 与 Agent 状态管理
```

## 项目原则

- 先用 Mock 建立确定性实验，再接入真实模型
- 先理解原始协议和运行机制，再引入 Agent 框架
- 不以“成功运行一次”作为完成标准
- 每个核心模块都验证正常、异常、超时和边界路径
- 对尚未实现的能力保持明确，不把规划包装成成果
