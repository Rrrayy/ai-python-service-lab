import asyncio
import json

import httpx

from src.ai_service.agent_loop import run_agent
from src.ai_service.providers import OpenAICompatibleProvider


def test_real_provider_agent_loop()->None:
	responses=[
		{
			"choices":[
				{
					"message":{
						"role":"assistant",
						"content":None,
						"tool_calls":[
							{
								"id":"call_progress_001",
								"type":"function",
								"function":{
									"name":"get_user_progress",
									"arguments":"{\"user_id\":1}"
								}
							},
							{
								"id":"call_progress_002",
								"type":"function",
								"function":{
									"name":"get_user_progress",
									"arguments":"{\"user_id\":2}"
								}
							}
						]
					},
					"finish_reason":"tool_calls"
				}
			],
			"usage":{
				"prompt_tokens":10,
				"completion_tokens":5,
				"total_tokens":15
			}
		},
		{
			"choices":[
				{
					"message":{
						"role":"assistant",
						"content":"已分别查询用户 1 和用户 2 的 Agent 学习进度。"
					},
					"finish_reason":"stop"
				}
			],
			"usage":{
				"prompt_tokens":30,
				"completion_tokens":12,
				"total_tokens":42
			}
		}
	]

	request_payloads=[]

	async def mock_handler(request:httpx.Request)->httpx.Response:
		payload=json.loads(request.content.decode("utf-8"))
		request_payloads.append(payload)
		return httpx.Response(200,json=responses.pop(0))

	async def run()->str:
		transport=httpx.MockTransport(mock_handler)
		async with httpx.AsyncClient(transport=transport) as http_client:
			provider=OpenAICompatibleProvider(
				base_url="https://example.com",
				api_key="test-key",
				http_client=http_client
			)
			content,_=await run_agent(
				provider,
				"我目前完成了多少个 Agent 学习任务？",
				max_model_calls=3
			)
			return content

	final_content=asyncio.run(run())

	assert final_content=="已分别查询用户 1 和用户 2 的 Agent 学习进度。"
	assert len(request_payloads)==2

	first_messages=request_payloads[0]["messages"]
	second_messages=request_payloads[1]["messages"]

	assert not any(
		message["role"]=="tool"
		for message in first_messages
	)

	assistant_messages=[
		message
		for message in second_messages
		if message["role"]=="assistant"
	]

	tool_messages=[
		message
		for message in second_messages
		if message["role"]=="tool"
	]

	assert len(assistant_messages)==1
	assert len(assistant_messages[0]["tool_calls"])==2
	assert len(tool_messages)==2

	assistant_call_ids={
		tool_call["id"]
		for tool_call in assistant_messages[0]["tool_calls"]
	}

	tool_result_ids={
		message["tool_call_id"]
		for message in tool_messages
	}

	assert assistant_call_ids=={
		"call_progress_001",
		"call_progress_002"
	}
	assert tool_result_ids==assistant_call_ids