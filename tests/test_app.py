from fastapi.testclient import TestClient

from src.ai_service.app import app
from src.ai_service.app import get_provider
from src.ai_service.providers import (
	ModelProvider,
	ModelRequest,
	ModelResponse,
	ProviderRateLimitError,
	ProviderTimeoutError,
	ProviderUpstreamError
)

class TimeoutProvider(ModelProvider):
	async def chat(
		self,
		request:ModelRequest,
	)->ModelResponse:
		raise ProviderTimeoutError(
			"内部模型请求超时"
		)


class RateLimitProvider(ModelProvider):
	async def chat(
		self,
		request:ModelRequest,
	)->ModelResponse:
		raise ProviderRateLimitError(
			"内部限流细节"
		)

class UpstreamProvider(ModelProvider):
	async def chat(
		self,
		request:ModelRequest,
	)->ModelResponse:
		raise ProviderUpstreamError(
			"上游服务返回 HTTP 503"
		)


class UnknownErrorProvider(ModelProvider):
	async def chat(
		self,
		request:ModelRequest,
	)->ModelResponse:
		raise RuntimeError(
			"数据库连接地址和内部堆栈"
		)
def test_health() -> None:
	with TestClient(app) as client:
		response=client.get("/health")

	assert response.status_code==200
	assert response.json()=={
		"status":"ok"
	}


def test_diagnosis_success() -> None:
	with TestClient(app) as client:
		response=client.post(
			"/v1/diagnosis",
			json={
				"content":"分析数据库连接池耗尽问题"
			},
		)

	body=response.json()

	assert response.status_code==200
	assert body["ok"] is True
	assert body["data"]["root_cause"]=="数据库连接池耗尽"
	assert body["request_id"]
	assert response.headers["X-Request-ID"]==body["request_id"]
	assert "X-Process-Time" in response.headers


def test_diagnosis_missing_content() -> None:
	with TestClient(app) as client:
		response=client.post(
			"/v1/diagnosis",
			json={},
		)

	assert response.status_code==422


def test_diagnosis_whitespace_content() -> None:
	with TestClient(app) as client:
		response=client.post(
			"/v1/diagnosis",
			json={
				"content":"   ",
			},
		)

	assert response.status_code==422

def test_model_timeout_returns_504() -> None:
	app.dependency_overrides[get_provider]=(
		lambda:TimeoutProvider()
	)

	try:
		with TestClient(app) as client:
			response=client.post(
				"/v1/diagnosis",
				json={
					"content":"分析数据库连接池耗尽问题"
				},
			)
	finally:
		app.dependency_overrides.clear()

	body=response.json()

	assert response.status_code==504
	assert body["ok"] is False
	assert body["error"]["code"]=="MODEL_TIMEOUT"
	assert body["request_id"]
	assert "内部模型请求超时" not in str(body)

def test_rate_limit_returns_429() -> None:
	app.dependency_overrides[get_provider]=(
		lambda:RateLimitProvider()
	)

	try:
		with TestClient(app) as client:
			response=client.post(
				"/v1/diagnosis",
				json={
					"content":"分析数据库连接池耗尽问题"
				},
			)
	finally:
		app.dependency_overrides.clear()

	body=response.json()

	assert response.status_code==429
	assert body["ok"] is False
	assert body["error"]["code"]=="MODEL_RATE_LIMITED"
	assert body["request_id"]
	assert "内部限流细节" not in str(body)


def test_upstream_error_returns_502() -> None:
	app.dependency_overrides[get_provider]=(
		lambda:UpstreamProvider()
	)

	try:
		with TestClient(app) as client:
			response=client.post(
				"/v1/diagnosis",
				json={
					"content":"分析数据库连接池耗尽问题"
				},
			)
	finally:
		app.dependency_overrides.clear()

	body=response.json()

	assert response.status_code==502
	assert body["ok"] is False
	assert body["error"]["code"]=="MODEL_UPSTREAM_ERROR"
	assert body["request_id"]
	assert "HTTP 503" not in str(body)


def test_unknown_error_returns_500() -> None:
	app.dependency_overrides[get_provider]=(
		lambda:UnknownErrorProvider()
	)

	try:
		with TestClient(app) as client:
			response=client.post(
				"/v1/diagnosis",
				json={
					"content":"分析数据库连接池耗尽问题"
				},
			)
	finally:
		app.dependency_overrides.clear()

	body=response.json()

	assert response.status_code==500
	assert body["ok"] is False
	assert body["error"]["code"]=="INTERNAL_ERROR"
	assert body["request_id"]
	assert "数据库连接地址" not in str(body)
	assert "内部堆栈" not in str(body)