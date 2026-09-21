# Agent Service Lab

一个基于 Python、FastAPI 和 OpenAI-compatible API 的 Agent 后端服务实验项目。

本项目实现并验证一条可测试的非流式 Agent 调用链：

```text
客户端请求
    ↓
FastAPI
    ↓
Agent Loop
    ├── Provider → 模型 API
    └── Tool Runtime → 注册工具
    ↓
结构化结果校验
    ↓
诊断业务结果
```

项目重点是清晰的模块边界、确定性的失败处理和可回归测试，不把模型输出直接当成可执行代码或可信业务结果。

## 核心能力

- `asyncio` 异步任务、超时、取消、并发和资源清理
- FastAPI 请求校验、依赖注入、异常处理、中间件和生命周期
- Pydantic 严格类型校验和业务规则校验
- OpenAI-compatible Provider 请求组装与响应解析
- Provider 网络、HTTP、认证、限流、上游和协议错误分层
- `ModelRequest`、`ModelResponse`、`Message`、`ToolCall`、`TokenUsage` 内部协议
- Tool Runtime 工具注册、参数校验、权限、超时、取消和并发执行
- Agent Loop 消息历史、工具调用、结果回填和二次模型调用
- 多工具调用的 `tool_call_id` 完整性验证
- Structured Output 的 JSON Schema 请求包装和本地校验
- DiagnoseReport 字段校验、业务规则校验和有限格式修复
- `httpx.MockTransport` 和 pytest 确定性测试

当前全量测试基线：

```text
43 passed
```

## 架构

```text
客户端
  ↓ HTTP
FastAPI
  ↓
Diagnose Service
  ↓
Agent Loop
  ├──→ Provider ──→ OpenAI-compatible Model API
  └──→ Tool Runtime ──→ Registered Tools
  ↓
ModelResponse.content
  ↓
DiagnosisReport 校验
  ↓
业务结果
```

### FastAPI

负责 HTTP 接入、请求参数校验、请求上下文、生命周期管理和外部错误响应。

### Diagnose Service

负责组织一次诊断业务：调用 Agent Loop、解析最终模型内容、执行有限结构化修复，并返回通过校验的 `DiagnosisReport`。

### Agent Loop

负责维护 `messages`，调用 Provider，识别 `tool_calls`，执行工具，回填 assistant/tool 消息，并控制模型调用次数。

### Provider

负责供应商请求组装、HTTP 调用、认证头、响应解析和 Provider 错误转换。Provider 不执行工具，也不判断诊断内容是否符合业务规则。

### Tool Runtime

负责工具白名单、参数模型、权限检查、超时、取消、业务异常和工具结果协议。

### Diagnosis

负责把模型最终返回的字符串解析成结构化报告，并执行字段、类型、范围和诊断业务规则校验。

## 项目结构

```text
src/ai_service/
├── app.py                    # FastAPI 应用、生命周期和请求中间件
├── async_basics.py           # asyncio 并发、超时、取消和背压实验
├── config.py                 # 环境变量配置和启动校验
├── providers.py              # Provider 抽象、内部协议和供应商适配
├── tools.py                  # Tool Runtime、工具注册表和工具执行器
├── agent_loop.py             # Agent Loop、消息追加和循环控制
├── diagnosis.py              # DiagnosisReport 和结构化业务校验
└── diagnosis_service.py      # 诊断业务流程和格式修复

tests/
├── test_async_basics.py
├── test_providers.py
├── test_tools.py
├── test_agent_loop.py
├── test_structured_output.py
└── test_diagnosis_service.py
```

## 环境要求

- Python 3.14
- Windows

安装依赖：

```powershell
E:\python\python3.14.0\python.exe -m pip install fastapi uvicorn httpx pydantic pydantic-settings pytest
```

## 运行和验证

运行全部测试：

```powershell
E:\python\python3.14.0\python.exe -m pytest -q
```

运行 Agent Loop 实验：

```powershell
E:\python\python3.14.0\python.exe -m src.ai_service.agent_loop
```

编译核心模块：

```powershell
E:\python\python3.14.0\python.exe -m py_compile src\ai_service\providers.py src\ai_service\tools.py src\ai_service\agent_loop.py src\ai_service\diagnosis.py src\ai_service\diagnosis_service.py
```

启动 FastAPI 开发服务：

```powershell
E:\python\python3.14.0\python.exe -m uvicorn src.ai_service.app:app --reload
```

## 测试覆盖

### Provider 测试

- 普通文本响应解析；
- 工具调用响应解析；
- 工具调用 ID、名称和 JSON arguments 校验；
- assistant 工具调用历史序列化；
- `response_schema` 到供应商 `response_format` 的包装；
- 请求超时、连接失败、HTTP 401、429、503；
- 非法 JSON、缺失 choices、空 choices 和非法响应结构。

### Tool Runtime 测试

- 正常工具执行；
- 未知工具；
- 参数类型错误和额外字段；
- 未认证调用；
- 工具超时；
- 工具执行异常；
- 外部取消和 `finally` 清理；
- 多工具并发以及逐个调用 ID 关联结果。

### Agent Loop 测试

- 模型返回多个工具调用；
- assistant/tool 消息因果链；
- 工具结果缺失、多出或重复；
- 工具结果回填后的二次模型调用；
- 最大模型调用次数；
- `tool_calls` 与普通 content 同时出现时优先处理工具调用。

### Diagnose 测试

- 合法 JSON 转为 `DiagnosisReport`；
- 非法 JSON、缺字段、类型错误、范围错误和额外字段；
- 高置信度报告的证据数量业务规则；
- 第一次结构化失败、第二次修复成功；
- 修复请求不携带工具并重新携带 Schema；
- 修复阶段返回工具调用或空内容；
- 修复失败后停止，不进行无限重试。

## 关键工程约束

```text
模型只能提出工具调用，不能直接执行本地函数。

Provider 只负责网络和供应商协议，不负责业务判断。

Agent Loop 结束不等于业务结果合格。

只有通过 DiagnosisReport 校验的结果才能作为成功业务结果。

结构化输出修复阶段禁止重新执行工具。

工具失败必须生成带原始 tool_call_id 的工具结果。

内部异常保留给日志，客户端只接收稳定错误协议。

所有重试都有次数、时间、Token 和成本边界。
```

## 当前限制

当前仓库仍是非流式 Agent Runtime 实验服务，以下能力尚未接入完整链路：

- 新版 Diagnose 业务尚未接入正式 FastAPI 诊断接口；
- SSE 流式输出和客户端断开处理；
- 真实模型 API 的完整 Function Calling 验证；
- Token、TTFT、TPOT、延迟和成本统计；
- 生产级持久化、鉴权、租户隔离和部署配置。

这些限制会在后续工程迭代中单独实现和验证，不将规划内容当作当前功能。
