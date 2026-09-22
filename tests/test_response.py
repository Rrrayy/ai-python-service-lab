from src.ai_service.response import (
	build_exception_response,
	build_success_response,
)
from src.ai_service.diagnosis import DiagnosisReport
from src.ai_service.providers import (
	ProviderAuthenticationError,
	ProviderProtocolError,
	ProviderRateLimitError,
	ProviderTimeoutError,
	ProviderUpstreamError,
)

from src.ai_service.diagnosis import StructuredOutputError
from src.ai_service.diagnosis_service import DiagnosisProtocolError
from src.ai_service.response import build_exception_response

def test_build_success_response() -> None:
	report=DiagnosisReport(
		root_cause="数据库连接池耗尽",
		confidence=0.92,
		evidence=[
			"连接数达到上限",
			"连接池活跃连接持续增长",
		],
		recommendations=[
			"检查连接释放逻辑",
		],
	)

	result=build_success_response(
		report,
		"req-001",
	)

	assert result=={
		"ok":True,
		"data":{
			"root_cause":"数据库连接池耗尽",
			"confidence":0.92,
			"evidence":[
				"连接数达到上限",
				"连接池活跃连接持续增长",
			],
			"recommendations":[
				"检查连接释放逻辑",
			],
		},
		"request_id":"req-001",
	}


def test_provider_timeout_is_safe() -> None:
	internal_error=ProviderTimeoutError(
		"ReadTimeout after 30 seconds; internal endpoint=/v1/chat/completions"
	)

	result=build_exception_response(
		internal_error,
		"req-002",
	)

	assert result=={
		"ok":False,
		"error":{
			"code":"MODEL_TIMEOUT",
			"message":"模型服务响应超时",
		},
		"request_id":"req-002",
	}

	assert "ReadTimeout" not in str(result)
	assert "internal endpoint" not in str(result)


def test_diagnosis_protocol_error_is_safe() -> None:
	internal_error=DiagnosisProtocolError(
		"模型返回字段 evidence 类型错误，内部校验失败"
	)

	result=build_exception_response(
		internal_error,
		"req-003",
	)

	assert result=={
		"ok":False,
		"error":{
			"code":"DIAGNOSIS_INVALID",
			"message":"模型返回的诊断结果无效",
		},
		"request_id":"req-003",
	}

	assert "evidence" not in str(result)
	assert "内部校验失败" not in str(result)

def test_unknown_error_is_hidden() -> None:
	internal_error=RuntimeError(
		"database password=secret; traceback=/internal/service/path"
	)

	result=build_exception_response(
		internal_error,
		"req-004",
	)

	assert result=={
		"ok":False,
		"error":{
			"code":"INTERNAL_ERROR",
			"message":"服务暂时不可用",
		},
		"request_id":"req-004",
	}

	assert "password" not in str(result)
	assert "secret" not in str(result)
	assert "traceback" not in str(result)
	assert "/internal/service/path" not in str(result)

def test_rate_limit_error() -> None:
	result=build_exception_response(
		ProviderRateLimitError("内部限流细节"),
		"req-rate",
	)

	assert result["ok"] is False
	assert result["error"]["code"]=="MODEL_RATE_LIMITED"
	assert "内部限流细节" not in str(result)

def test_authentication_error() -> None:
	result=build_exception_response(
		ProviderAuthenticationError("API key=secret"),
		"req-auth",
	)

	assert result["error"]["code"]=="MODEL_AUTHENTICATION_FAILED"
	assert "secret" not in str(result)

def test_provider_protocol_error() -> None:
	result=build_exception_response(
		ProviderProtocolError("供应商原始响应包含敏感字段"),
		"req-protocol",
	)

	assert result["error"]["code"]=="MODEL_INVALID_RESPONSE"
	assert "敏感字段" not in str(result)

def test_structured_output_error() -> None:
	result=build_exception_response(
		StructuredOutputError(
			"INVALID_STRUCTURED_OUTPUT",
			"内部字段校验详情",
		),
		"req-structured",
	)

	assert result["error"]["code"]=="DIAGNOSIS_INVALID"
	assert "内部字段校验详情" not in str(result)