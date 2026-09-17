import json

from .tools import execute_tool_calls,tool_registry
from collections import  Counter

class ScriptedProvider:
	def __init__(self)->None:
		self.call_count=0

	async def chat(self,messages:list[dict])->dict:
		self.call_count+=1

		if self.call_count == 1:
			return {
				"content": None,
				"tool_calls": [
					{
						"id": "call_progress_001",
						"type": "function",
						"function": {
							"name": "get_user_progress",
							"arguments": '{"user_id":1}'
						}
					},
					{
						"id": "call_progress_002",
						"type": "function",
						"function": {
							"name": "get_user_progress",
							"arguments": '{"user_id":2}'
						}
					}
				],
				"finish_reason": "tool_calls"
			}

		if self.call_count==2:
			has_progress_call = any(
				message["role"] == "assistant"
				and any(
					tool_call["id"] == "call_progress_001"
					for tool_call in message.get("tool_calls",[])
				)
				for message in messages
			)

			expected_ids = {
				"call_progress_001",
				"call_progress_002"
			}

			returned_ids = {
				message["tool_call_id"]
				for message in messages
				if message["role"] == "tool"
			}
			if not has_progress_call:
				raise RuntimeError("第二次模型调用前缺少 assistant 工具调用记录")

			if not expected_ids.issubset(returned_ids):
				raise RuntimeError("第二次模型调用前缺少学习进度工具结果")



			return {
				"content": "已分别查询用户 1 和用户 2 的 Agent 学习进度。",
				"tool_calls": [],
				"finish_reason": "stop"
			}

		raise RuntimeError("Mock Provider 收到了超出预期的模型调用")

def validate_tool_results(tool_calls:list[dict],tool_results:list[dict])->None:
	requested_ids=[tool_call["id"] for tool_call in tool_calls]
	result_ids=[tool_result["tool_call_id"] for tool_result in tool_results]

	requested_counts=Counter(requested_ids)
	result_counts=Counter(result_ids)

	if any(count>1 for count in requested_counts.values()):
		raise RuntimeError("模型返回了重复的 tool_call_id")

	if result_counts!=requested_counts:
		missing_ids=list((requested_counts-result_counts).elements())
		unexpected_ids=list((result_counts-requested_counts).elements())
		raise RuntimeError(f"工具结果与调用不匹配，缺少={missing_ids}，多出={unexpected_ids}")

async def run_agent(
		provider: ScriptedProvider,
		user_content: str,
		max_model_calls: int
) -> tuple[str, list[dict]]:
	messages = [
		{
			"role": "system",
			"content": "你是学习助手，只能依据工具结果回答。"
		},
		{
			"role": "user",
			"content": user_content
		}
	]

	for _ in range(max_model_calls):
		model_response = await provider.chat(messages)
		tool_calls = model_response["tool_calls"]

		assistant_message = {
			"role": "assistant",
			"content": model_response["content"]
		}
		if tool_calls:
			assistant_message["tool_calls"] = tool_calls

		messages.append(assistant_message)

		if tool_calls:
			tool_results = await execute_tool_calls(
				tool_calls,
				tool_registry,
				is_authenticated=True
			)
			validate_tool_results(tool_calls, tool_results)
			messages.extend(tool_results)
			continue

		content = model_response["content"]
		if content:
			return content, messages

		raise RuntimeError("模型既没有返回工具调用，也没有返回最终文本")

	raise RuntimeError("超过最大模型调用次数")

async def main() -> None:
	provider = ScriptedProvider()
	final_content, messages = await run_agent(
		provider,
		"我目前完成了多少个 Agent 学习任务？",
		max_model_calls=3
	)

	print(f"最终回答：{final_content}")
	print("执行轨迹：")
	for message in messages:
		print(json.dumps(message, ensure_ascii=False))

if __name__ == "__main__":
	import asyncio
	asyncio.run(main())