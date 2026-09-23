import json
import re
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from typing import Annotated
from fastapi import Depends,FastAPI,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field,StringConstraints

from .config import Settings,validate_settings
from .diagnosis_handler import handle_diagnosis
from .providers import (
	ModelProvider,
	MockProvider,
	OpenAICompatibleProvider,
)


from typing import Annotated

from pydantic import BaseModel,StringConstraints


class DiagnosisRequest(BaseModel):
	content:Annotated[
		str,
		StringConstraints(
			strip_whitespace=True,
			min_length=1,
			max_length=10000,
		),
	]


REQUEST_ID_PATTERN=re.compile(
	r"^[A-Za-z0-9._-]{1,64}$"
)


def new_request_id()->str:
	# 生成当前请求的新 ID
	return uuid.uuid4().hex


def resolve_request_id(request:Request)->str:
	# 读取客户端传入的请求 ID
	client_request_id=request.headers.get(
		"X-Request-ID"
	)
	# 只有符合规则的请求 ID 才允许透传
	if (
		client_request_id is not None
		and REQUEST_ID_PATTERN.fullmatch(client_request_id)
	):
		return client_request_id

	# 客户端没有传入或格式非法时由服务端生成
	return new_request_id()


def get_provider(request:Request)->ModelProvider:
	# 从应用生命周期保存的状态中获取 Provider
	return request.app.state.provider


def get_request_id(request:Request)->str:
	# 获取请求中间件提前保存的 request_id
	return request.state.request_id


def build_provider(
	settings:Settings,
	http_client:httpx.AsyncClient,
)->ModelProvider:
	# mock 模式使用确定性的本地 Provider
	if settings.provider=="mock":
		return MockProvider()

	# 真实 Provider 使用 OpenAI-compatible HTTP 接口
	if settings.api_key is None or settings.base_url is None:
		raise RuntimeError(
			"真实模型缺少 API Key 或 Base URL"
		)

	return OpenAICompatibleProvider(
		base_url=settings.base_url,
		api_key=settings.api_key,
		http_client=http_client,
	)


@asynccontextmanager
async def lifespan(app:FastAPI):
	# 读取环境变量和配置文件
	settings=Settings()

	# 启动时验证配置是否满足当前 Provider 要求
	validate_settings(settings)

	# 创建应用生命周期内共享的 HTTP 客户端
	http_client=httpx.AsyncClient(
		timeout=settings.timeout
	)

	try:
		# 在应用启动时创建 Provider
		provider=build_provider(
			settings=settings,
			http_client=http_client,
		)

		# 将共享对象放入 app.state
		app.state.settings=settings
		app.state.provider=provider
		app.state.http_client=http_client

		# 让 FastAPI 进入运行状态
		yield

	finally:
		# 应用关闭时释放 HTTP 连接池
		await http_client.aclose()


app=FastAPI(
	title="Agent Service Lab",
	version="1.0.0",
	lifespan=lifespan,
)


@app.middleware("http")
async def request_context(
	request:Request,
	call_next,
):
	# 为当前 HTTP 请求生成或读取 request_id
	request_id=resolve_request_id(request)

	# 将 request_id 放进当前请求上下文
	request.state.request_id=request_id

	# 记录请求开始时间
	start_time=time.perf_counter()

	# 执行真正的路由函数
	response=await call_next(request)

	# 计算请求处理耗时
	elapsed_ms=(
		time.perf_counter()-start_time
	)*1000

	# 把请求 ID 和耗时返回给客户端
	response.headers["X-Request-ID"]=request_id
	response.headers["X-Process-Time"]=(
		f"{elapsed_ms:.2f}"
	)

	# 输出最小结构化访问日志
	print(
		json.dumps(
			{
				"request_id":request_id,
				"method":request.method,
				"path":request.url.path,
				"status_code":response.status_code,
				"elapsed_ms":round(elapsed_ms,2),
			},
			ensure_ascii=False,
		)
	)

	# 返回 HTTP 响应
	return response


def resolve_status_code(result:dict)->int:
	# 业务成功统一对应 HTTP 200
	if result.get("ok") is True:
		return 200

	# 从统一错误响应中读取业务错误码
	error=result.get("error",{})
	error_code=error.get("code")

	# 业务错误码到 HTTP 状态码的映射
	status_code_map={
		"MODEL_TIMEOUT":504,
		"MODEL_RATE_LIMITED":429,
		"MODEL_AUTHENTICATION_FAILED":502,
		"MODEL_UPSTREAM_ERROR":502,
		"MODEL_INVALID_RESPONSE":502,
		"DIAGNOSIS_INVALID":502,
		"INTERNAL_ERROR":500,
	}

	# 未知错误默认按照服务器内部错误处理
	return status_code_map.get(
		error_code,
		500,
	)


def to_http_response(result:dict)->JSONResponse:
	# 根据业务结果决定 HTTP 状态码
	status_code=resolve_status_code(result)

	# 将统一结果字典包装为真正的 HTTP JSON 响应
	return JSONResponse(
		status_code=status_code,
		content=result,
	)


@app.get("/health")
async def health()->dict[str,str]:
	# 提供基础健康检查接口
	return {
		"status":"ok"
	}


@app.post("/v1/diagnosis")
async def create_diagnosis(
	request:DiagnosisRequest,
	provider:ModelProvider=Depends(get_provider),
	request_id:str=Depends(get_request_id),
)->JSONResponse:
	# 调用业务连接层，不在 API 层处理模型和工具细节
	result=await handle_diagnosis(
		provider=provider,
		user_content=request.content,
		request_id=request_id,
	)

	# 将业务结果转换为 HTTP 状态码和 JSON 响应
	return to_http_response(result)