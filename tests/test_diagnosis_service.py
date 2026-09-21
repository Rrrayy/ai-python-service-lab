import asyncio

import pytest

from src.ai_service.diagnosis import (
	DiagnosisReport,
	StructuredOutputError,
	get_diagnosis_schema,
)
from src.ai_service.diagnosis_service import diagnose_issue
from src.ai_service.providers import ModelProvider,ModelRequest,ModelResponse

class AlwaysInvalidDiagnosisProvider(ModelProvider):
	def __init__(self)->None:
		self.call_count=0
		self.requests=[]

	async def chat(self,request:ModelRequest)->ModelResponse:
		self.call_count+=1
		self.requests.append(request)

		return ModelResponse(
			content='{"root_cause":"数据库连接池耗尽"}',
			finish_reason="stop"
		)

class RepairDiagnosisProvider(ModelProvider):
	def __init__(self)->None:
		self.call_count=0
		self.requests=[]

	async def chat(self,request:ModelRequest)->ModelResponse:
		self.call_count+=1
		self.requests.append(request)

		if self.call_count==1:
			return ModelResponse(
				content='{"root_cause":"数据库连接池耗尽"}',
				finish_reason="stop"
			)

		return ModelResponse(
			content=(
				'{"root_cause":"数据库连接池耗尽",'
				'"confidence":0.92,'
				'"evidence":["活跃连接数达到上限","请求等待连接超时"],'
				'"recommendations":["检查连接释放路径","核对连接池容量"]}'
			),
			finish_reason="stop"
		)

class ValidDiagnosisProvider(ModelProvider):
	def __init__(self)->None:
		self.call_count=0

	async def chat(self,request:ModelRequest)->ModelResponse:
		self.call_count+=1

		return ModelResponse(
			content=(
				'{"root_cause":"数据库连接池耗尽",'
				'"confidence":0.92,'
				'"evidence":["活跃连接数达到上限","请求等待连接超时"],'
				'"recommendations":["检查连接释放路径","核对连接池容量"]}'
			),
			finish_reason="stop"
		)


def test_diagnose_issue_returns_report()->None:
	provider=ValidDiagnosisProvider()

	report=asyncio.run(
		diagnose_issue(
			provider=provider,
			user_content="服务出现数据库连接超时",
			max_model_calls=3
		)
	)

	assert isinstance(report,DiagnosisReport)
	assert report.root_cause=="数据库连接池耗尽"
	assert report.confidence==0.92
	assert len(report.evidence)==2
	assert len(report.recommendations)==2
	assert provider.call_count==1

def test_diagnose_issue_repairs_invalid_output()->None:
	provider=RepairDiagnosisProvider()

	report=asyncio.run(
		diagnose_issue(
			provider=provider,
			user_content="服务出现数据库连接超时",
			max_model_calls=3
		)
	)

	assert isinstance(report,DiagnosisReport)
	assert report.root_cause=="数据库连接池耗尽"
	assert report.confidence==0.92
	assert len(report.evidence)==2
	assert len(report.recommendations)==2
	assert provider.call_count==2

	repair_request=provider.requests[1]

	assert repair_request.tools==[]
	assert repair_request.response_schema==get_diagnosis_schema()
	assert repair_request.temperature==0.0
	assert repair_request.messages[-1].role=="user"
	assert "重新输出" in repair_request.messages[-1].content


def test_diagnose_issue_stops_after_repair_failure()->None:
	provider=AlwaysInvalidDiagnosisProvider()

	with pytest.raises(StructuredOutputError) as error_info:
		asyncio.run(
			diagnose_issue(
				provider=provider,
				user_content="服务出现数据库连接超时",
				max_model_calls=3
			)
		)

	assert error_info.value.error_code=="INVALID_STRUCTURED_OUTPUT"
	assert provider.call_count==2

	repair_request=provider.requests[1]

	assert repair_request.tools==[]
	assert repair_request.response_schema==get_diagnosis_schema()
	assert repair_request.temperature==0.0