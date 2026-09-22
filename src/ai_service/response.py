from typing import Any

from pydantic import BaseModel

from .diagnosis import DiagnosisReport,StructuredOutputError
from .diagnosis_service import DiagnosisProtocolError
from .providers import (
	ProviderAuthenticationError,
	ProviderProtocolError,
	ProviderRateLimitError,
	ProviderTimeoutError,
	ProviderUpstreamError,
)

class SuccessResponse(BaseModel):
	ok:bool=True
	data:DiagnosisReport
	request_id:str

class ErrorData(BaseModel):
	# 表示客户端看到的稳定错误信息
	code:str
	message:str


class ErrorResponse(BaseModel):
	# 表示客户端看到的失败响应
	ok:bool=False
	error:ErrorData
	request_id:str


def build_success_response(
		report: DiagnosisReport,
		request_id: str,
) -> dict[str, Any]:
	# 将内部诊断对象转换为客户端成功响应
	response = SuccessResponse(
		data=report,
		request_id=request_id,
	)

	# 将 Pydantic 对象转换成普通字典
	return response.model_dump()


def build_error_response(
	code:str,
	message:str,
	request_id:str,
)->dict[str,Any]:
	# 创建稳定的客户端错误结构
	response=ErrorResponse(
		error=ErrorData(
			code=code,
			message=message,
		),
		request_id=request_id,
	)

	# 返回普通字典，方便 FastAPI 序列化
	return response.model_dump()


def map_exception_to_error(error:Exception)->tuple[str,str]:
	if isinstance(error,ProviderAuthenticationError):
		return (
			"MODEL_AUTHENTICATION_FAILED",
			"模型服务认证失败",
		)

	if isinstance(error,ProviderRateLimitError):
		return (
			"MODEL_RATE_LIMITED",
			"模型服务请求过于频繁",
		)

	if isinstance(error,ProviderTimeoutError):
		return (
			"MODEL_TIMEOUT",
			"模型服务响应超时",
		)

	if isinstance(error,ProviderUpstreamError):
		return (
			"MODEL_UPSTREAM_ERROR",
			"模型服务暂时不可用",
		)

	if isinstance(error,ProviderProtocolError):
		return (
			"MODEL_INVALID_RESPONSE",
			"模型服务返回格式异常",
		)

	if isinstance(error,StructuredOutputError):
		return (
			"DIAGNOSIS_INVALID",
			"模型返回的诊断结果无效",
		)

	if isinstance(error,DiagnosisProtocolError):
		return (
			"DIAGNOSIS_INVALID",
			"模型返回的诊断结果无效",
		)

	return (
		"INTERNAL_ERROR",
		"服务暂时不可用",
	)

def build_exception_response(
	error:Exception,
	request_id:str,
)->dict[str,Any]:
	# 将内部异常转换成外部错误码和安全消息
	error_code,message=map_exception_to_error(error)

	# 生成统一错误响应
	return build_error_response(
		error_code,
		message,
		request_id,
	)


def main()->None:
	# 构造一个合法诊断结果
	report = DiagnosisReport(
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
	# 验证成功响应
	success=build_success_response(
		report,
		"req-success",
	)
	print(success)

	# 验证超时错误响应
	timeout=build_exception_response(
		ProviderTimeoutError("内部异常细节"),
		"req-timeout",
	)
	print(timeout)

	# 验证未知异常响应
	unknown=build_exception_response(
		RuntimeError("数据库连接地址和内部堆栈"),
		"req-unknown",
	)
	print(unknown)


if __name__=="__main__":
	main()