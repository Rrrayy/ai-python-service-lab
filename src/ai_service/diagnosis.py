import json
from typing import Any

from pydantic import BaseModel,ConfigDict,Field,ValidationError


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


class DiagnosisBusinessError(Exception):
	pass


class DiagnosisReport(BaseModel):
	model_config=ConfigDict(strict=True,extra="forbid")
	root_cause:str
	confidence:float=Field(ge=0,le=1)
	evidence:list[str]=Field(min_length=1)
	recommendations:list[str]=Field(min_length=1)


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


def get_diagnosis_schema()->dict[str,Any]:
	return DiagnosisReport.model_json_schema()