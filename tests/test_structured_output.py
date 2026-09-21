import json
import asyncio
import pytest
from pydantic import BaseModel, Field, ValidationError, ConfigDict

class StructuredOutputError(Exception):
	def __init__(
			self,
			error_code:str,
			message:str,
			cause:Exception|None=None
	)->None:
		super().__init__(message)
		self.error_code=error_code
		self.cause=cause

class DiagnosisReport(BaseModel):
	model_config = ConfigDict(strict=True,extra='forbid')
	root_cause:str
	confidence:float=Field(ge=0,le=1)
	evidence:list[str]=Field(min_length=1)
	recommendations:list[str]=Field(min_length=1)

class DiagnosisBusinessError(Exception):
	pass


def validate_diagnosis_business(report:DiagnosisReport)->None:
	if report.confidence>=0.8 and len(report.evidence)<2:
		raise DiagnosisBusinessError(
			"高置信度诊断至少需要两条证据"
		)

def parse_diagnosis(content:str)->DiagnosisReport:
	try:
		data=json.loads(content)
	except json.JSONDecodeError as error:
		raise StructuredOutputError(
			"INVALID_STRUCTURED_OUTPUT",
			"模型输出不是合法JSON",
			error
		) from error

	try:
		report=DiagnosisReport.model_validate(data)
	except ValidationError as error:
		raise StructuredOutputError(
			"INVALID_STRUCTURED_OUTPUT",
			"模型输出不符合诊断报告格式",
			error
		) from error

	try:
		validate_diagnosis_business(report)
	except DiagnosisBusinessError as error:
		raise StructuredOutputError(
			"INVALID_STRUCTURED_OUTPUT",
			"模型诊断结果不符合业务规则",
			error
		) from error

	return report

def test_valid_diagnosis()->None:
	content=json.dumps({
		"root_cause":"数据库连接池耗尽",
		"confidence":0.92,
		"evidence":[
			"活跃连接数持续达到上限",
			"请求等待连接的时间增加"
		],
		"recommendations":[
			"检查连接释放路径",
			"核对连接池容量"
		]
	},ensure_ascii=False)

	report=parse_diagnosis(content)

	assert report.root_cause=="数据库连接池耗尽"
	assert report.confidence==0.92
	assert report.evidence==[
		"活跃连接数持续达到上限",
		"请求等待连接的时间增加"
	]


def test_invalid_json()->None:
	content='{"root_cause":"数据库连接池耗尽"'

	with pytest.raises(StructuredOutputError) as error_info:
		parse_diagnosis(content)

	assert error_info.value.error_code == "INVALID_STRUCTURED_OUTPUT"
	assert isinstance(
		error_info.value.cause,
		json.JSONDecodeError
	)

def test_confidence_out_of_range()->None:
	content=json.dumps({
		"root_cause":"数据库连接池耗尽",
		"confidence":1.5,
		"evidence":["连接池达到上限"],
		"recommendations":["检查连接释放"]
	},ensure_ascii=False)

	with pytest.raises(StructuredOutputError) as error_info:
		parse_diagnosis(content)

	assert error_info.value.error_code=="INVALID_STRUCTURED_OUTPUT"
	assert isinstance(
		error_info.value.cause,
		ValidationError
	)

def test_missing_required_field()->None:
	content=json.dumps({
		"root_cause":"数据库连接池耗尽",
		"confidence":0.92,
		"evidence":["连接池达到上限"]
	},ensure_ascii=False)

	with pytest.raises(StructuredOutputError) as error_info:
		parse_diagnosis(content)

	assert error_info.value.error_code=="INVALID_STRUCTURED_OUTPUT"
	assert isinstance(error_info.value.cause,ValidationError)


def test_empty_evidence()->None:
	content=json.dumps({
		"root_cause":"数据库连接池耗尽",
		"confidence":0.92,
		"evidence":[],
		"recommendations":["检查连接释放"]
	},ensure_ascii=False)

	with pytest.raises(StructuredOutputError) as error_info:
		parse_diagnosis(content)

	assert error_info.value.error_code=="INVALID_STRUCTURED_OUTPUT"
	assert isinstance(error_info.value.cause,ValidationError)

def test_extra_field()->None:
	content=json.dumps({
		"root_cause":"数据库连接池耗尽",
		"confidence":0.92,
		"evidence":["连接池达到上限"],
		"recommendations":["检查连接释放"],
		"debug_info":"内部信息"
	},ensure_ascii=False)

	with pytest.raises(StructuredOutputError) as error_info:
		parse_diagnosis(content)

	assert error_info.value.error_code=="INVALID_STRUCTURED_OUTPUT"
	assert isinstance(error_info.value.cause,ValidationError)

def test_confidence_string()->None:
	content=json.dumps({
		"root_cause":"数据库连接池耗尽",
		"confidence":"0.92",
		"evidence":["连接池达到上限"],
		"recommendations":["检查连接释放"]
	},ensure_ascii=False)

	with pytest.raises(StructuredOutputError) as error_info:
		parse_diagnosis(content)

	assert error_info.value.error_code=="INVALID_STRUCTURED_OUTPUT"
	assert isinstance(error_info.value.cause,ValidationError)

def test_high_confidence_requires_two_evidence()->None:
	content=json.dumps({
		"root_cause":"数据库连接池耗尽",
		"confidence":0.95,
		"evidence":["连接池达到上限"],
		"recommendations":["检查连接释放"]
	},ensure_ascii=False)

	with pytest.raises(StructuredOutputError) as error_info:
		parse_diagnosis(content)

	assert error_info.value.error_code=="INVALID_STRUCTURED_OUTPUT"
	assert isinstance(
		error_info.value.cause,
		DiagnosisBusinessError
	)

def to_error_response(error:StructuredOutputError)->dict:
	return {
		"ok":False,
		"error_code":error.error_code,
		"message":str(error)
	}

def test_error_response_does_not_expose_cause()->None:
	content='{"root_cause":"数据库连接池耗尽"'

	with pytest.raises(StructuredOutputError) as error_info:
		parse_diagnosis(content)

	response=to_error_response(error_info.value)

	assert response=={
		"ok":False,
		"error_code":"INVALID_STRUCTURED_OUTPUT",
		"message":"模型输出不是合法JSON"
	}
	assert "cause" not in response


async def retry_model(attempt:int)->str:
	if attempt==0:
		return json.dumps({
			"root_cause":"数据库连接池耗尽",
			"confidence":1.5,
			"evidence":["连接池达到上限"],
			"recommendations":["检查连接释放"]
		},ensure_ascii=False)

	return json.dumps({
		"root_cause":"数据库连接池耗尽",
		"confidence":0.92,
		"evidence":[
			"活跃连接数持续达到上限",
			"请求等待连接的时间增加"
		],
		"recommendations":[
			"检查连接释放路径",
			"核对连接池容量"
		]
	},ensure_ascii=False)


async def parse_with_retry(max_attempts:int)->DiagnosisReport:
	for attempt in range(max_attempts):
		content=await retry_model(attempt)

		try:
			return parse_diagnosis(content)
		except StructuredOutputError:
			if attempt==max_attempts-1:
				raise

	raise RuntimeError("结构化输出重试逻辑异常")

def test_structured_output_retry_success()->None:
	report=asyncio.run(parse_with_retry(max_attempts=2))

	assert report.root_cause=="数据库连接池耗尽"
	assert report.confidence==0.92
	assert len(report.evidence)==2

async def always_invalid_model()->str:
	return json.dumps({
		"root_cause":"数据库连接池耗尽",
		"confidence":1.5,
		"evidence":["连接池达到上限"],
		"recommendations":["检查连接释放"]
	},ensure_ascii=False)

async def parse_with_exhausted_retry(
		max_attempts:int
)->DiagnosisReport:
	for attempt in range(max_attempts):
		content=await always_invalid_model()

		try:
			return parse_diagnosis(content)
		except StructuredOutputError:
			if attempt==max_attempts-1:
				raise

	raise RuntimeError("结构化输出重试逻辑异常")


def test_structured_output_retry_exhausted()->None:
	with pytest.raises(StructuredOutputError) as error_info:
		asyncio.run(
			parse_with_exhausted_retry(max_attempts=2)
		)

	assert error_info.value.error_code=="INVALID_STRUCTURED_OUTPUT"
	assert isinstance(
		error_info.value.cause,
		ValidationError
	)