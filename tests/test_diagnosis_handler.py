import asyncio

from src.ai_service.diagnosis_handler import handle_diagnosis
from src.ai_service.providers import (
	ModelProvider,
	ModelResponse,
	MockProvider,
)


def test_handle_diagnosis_success() -> None:
	provider=MockProvider()

	result=asyncio.run(
		handle_diagnosis(
			provider=provider,
			user_content="分析数据库连接池耗尽问题",
			request_id="req-test-success",
		)
	)

	assert result["ok"] is True
	assert result["request_id"]=="req-test-success"
	assert result["data"]["root_cause"]=="数据库连接池耗尽"
	assert len(result["data"]["evidence"])>=2


class InvalidDiagnosisProvider(ModelProvider):
	async def chat(self,request):
		return ModelResponse(
			content="这不是合法的诊断 JSON",
			finish_reason="stop",
		)


def test_handle_diagnosis_failure() -> None:
	provider=InvalidDiagnosisProvider()

	result=asyncio.run(
		handle_diagnosis(
			provider=provider,
			user_content="分析数据库连接池耗尽问题",
			request_id="req-test-failure",
		)
	)

	assert result["ok"] is False
	assert result["request_id"]=="req-test-failure"
	assert result["error"]["code"]=="DIAGNOSIS_INVALID"
	assert "合法的诊断 JSON" not in str(result)