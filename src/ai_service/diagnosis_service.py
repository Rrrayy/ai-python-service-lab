from typing import Any

from .agent_loop import build_model_request,run_agent
from .diagnosis import (
	DiagnosisReport,
	StructuredOutputError,
	get_diagnosis_schema,
	parse_diagnosis,
)
from .providers import ModelProvider,ModelRequest


class DiagnosisProtocolError(Exception):
	pass

async def diagnose_issue(
	provider:ModelProvider,
	user_content:str,
	max_model_calls:int=3,
)->DiagnosisReport:
	final_content,messages=await run_agent(
		provider=provider,
		user_content=user_content,
		max_model_calls=max_model_calls,
	)

	try:
		return parse_diagnosis(final_content)
	except StructuredOutputError:
		repaired_content=await repair_diagnosis_output(
			provider=provider,
			messages=messages,
		)
		return parse_diagnosis(repaired_content)


async def repair_diagnosis_output(
	provider:ModelProvider,
	messages:list[dict[str,Any]],
)->str:
	messages.append({
		"role":"user",
		"content":(
			"上一条诊断结果没有通过本地校验。"
			"请基于已有上下文重新输出诊断报告。"
			"只输出符合 JSON Schema 的 JSON，"
			"不要输出 Markdown、解释文字或工具调用。"
		)
	})

	base_request=build_model_request(messages)

	request=ModelRequest(
		model=base_request.model,
		messages=base_request.messages,
		tools=[],
		response_schema=get_diagnosis_schema(),
		temperature=0.0,
		stream=False,
	)

	response=await provider.chat(request)

	if response.tool_calls:
		raise DiagnosisProtocolError(
			"诊断修复阶段不允许工具调用"
		)

	if response.content is None or not response.content.strip():
		raise DiagnosisProtocolError(
			"诊断修复阶段没有返回内容"
		)

	messages.append({
		"role":"assistant",
		"content":response.content,
	})

	return response.content