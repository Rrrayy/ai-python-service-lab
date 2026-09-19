import asyncio
from collections.abc import Awaitable,Callable

import httpx
import pytest

from src.ai_service.providers import (
	Message,
	ModelResponse,
	ModelRequest,
	OpenAICompatibleProvider,
	ProviderAuthenticationError,
	ProviderProtocolError,
	ProviderRateLimitError,
	ProviderTimeoutError,
	ProviderUpstreamError
)

def create_request()->ModelRequest:
	return ModelRequest(
		model="mock-model",
		messages=[
			Message(
				role="user",
				content="你好"
			)
		],
		temperature=0.7
	)

async def run_provider(
	mock_handler:Callable[[httpx.Request],Awaitable[httpx.Response]]
)->ModelResponse:
	transport=httpx.MockTransport(mock_handler)
	async with httpx.AsyncClient(transport=transport) as http_client:
		provider=OpenAICompatibleProvider(
			base_url="https://example.com",
			api_key="test-key",
			http_client=http_client
		)
		return await provider.chat(create_request())

async def call_with_status(status_code:int)->None:
	async def mock_handler(request:httpx.Request)->httpx.Response:
		return httpx.Response(
			status_code,
			json={
				"error":{
					"message":"模拟上游错误"
				}
			}
		)
	await run_provider(mock_handler)


def test_authentication_error()->None:
	with pytest.raises(ProviderAuthenticationError):
		asyncio.run(call_with_status(401))


def test_rate_limit_error()->None:
	with pytest.raises(ProviderRateLimitError):
		asyncio.run(call_with_status(429))


def test_upstream_error()->None:
	with pytest.raises(ProviderUpstreamError):
		asyncio.run(call_with_status(503))


async def call_timeout()->None:
	async def mock_handler(request:httpx.Request)->httpx.Response:
		raise httpx.ReadTimeout("模拟读取超时")
	await run_provider(mock_handler)


async def call_network_error()->None:
	async def mock_handler(request:httpx.Request)->httpx.Response:
		raise httpx.ConnectError("模拟连接失败")
	await run_provider(mock_handler)


def test_timeout_error()->None:
	with pytest.raises(ProviderTimeoutError):
		asyncio.run(call_timeout())


def test_network_error()->None:
	with pytest.raises(ProviderUpstreamError):
		asyncio.run(call_network_error())



async def call_invalid_json()->None:
	async def mock_handler(request:httpx.Request)->httpx.Response:
		return httpx.Response(
			200,
			content=b"this is not json",
			headers={
				"Content-Type":"application/json"
			}
		)
	await run_provider(mock_handler)


async def call_empty_choices()->None:
	async def mock_handler(request:httpx.Request)->httpx.Response:
		return httpx.Response(
			200,
			json={
				"choices":[]
			}
		)
	await run_provider(mock_handler)


async def call_missing_choices()->None:
	async def mock_handler(request:httpx.Request)->httpx.Response:
		return httpx.Response(
			200,
			json={
				"usage":{
					"prompt_tokens":10,
					"completion_tokens":5,
					"total_tokens":15
				}
			}
		)
	await run_provider(mock_handler)


def test_invalid_json_error()->None:
	with pytest.raises(ProviderProtocolError):
		asyncio.run(call_invalid_json())


def test_empty_choices_error()->None:
	with pytest.raises(ProviderProtocolError):
		asyncio.run(call_empty_choices())


def test_missing_choices_error()->None:
	with pytest.raises(ProviderProtocolError):
		asyncio.run(call_missing_choices())

def create_tool_response(tool_call:dict)->dict:
	return {
		"choices":[
			{
				"message":{
					"role":"assistant",
					"content":None,
					"tool_calls":[tool_call]
				},
				"finish_reason":"tool_calls"
			}
		]
	}


async def call_tool_response(tool_call:dict)->ModelResponse:
	async def mock_handler(request:httpx.Request)->httpx.Response:
		return httpx.Response(
			200,
			json=create_tool_response(tool_call)
		)

	return await run_provider(mock_handler)


def test_tool_calls_must_be_list()->None:
	async def run()->None:
		async def mock_handler(request:httpx.Request)->httpx.Response:
			return httpx.Response(
				200,
				json={
					"choices":[
						{
							"message":{
								"role":"assistant",
								"content":None,
								"tool_calls":{}
							},
							"finish_reason":"tool_calls"
						}
					]
				}
			)

		await run_provider(mock_handler)

	with pytest.raises(ProviderProtocolError):
		asyncio.run(run())


def test_tool_call_id_required()->None:
	with pytest.raises(ProviderProtocolError):
		asyncio.run(
			call_tool_response(
				{
					"type":"function",
					"function":{
						"name":"get_user_progress",
						"arguments":"{\"user_id\":1}"
					}
				}
			)
		)


def test_tool_name_required()->None:
	with pytest.raises(ProviderProtocolError):
		asyncio.run(
			call_tool_response(
				{
					"id":"call_001",
					"type":"function",
					"function":{
						"arguments":"{\"user_id\":1}"
					}
				}
			)
		)


def test_tool_arguments_must_be_json()->None:
	with pytest.raises(ProviderProtocolError):
		asyncio.run(
			call_tool_response(
				{
					"id":"call_001",
					"type":"function",
					"function":{
						"name":"get_user_progress",
						"arguments":"{user_id:1}"
					}
				}
			)
		)


def test_tool_arguments_must_be_object()->None:
	with pytest.raises(ProviderProtocolError):
		asyncio.run(
			call_tool_response(
				{
					"id":"call_001",
					"type":"function",
					"function":{
						"name":"get_user_progress",
						"arguments":"[1,2,3]"
					}
				}
			)
		)


async def call_text_response()->ModelResponse:
	async def mock_handler(request:httpx.Request)->httpx.Response:
		return httpx.Response(
			200,
			json={
				"choices":[
					{
						"message":{
							"role":"assistant",
							"content":"你好，这是模型回答"
						},
						"finish_reason":"stop"
					}
				],
				"usage":{
					"prompt_tokens":10,
					"completion_tokens":5,
					"total_tokens":15
				}
			}
		)

	return await run_provider(mock_handler)


def test_text_response()->None:
	response=asyncio.run(call_text_response())

	assert response.content=="你好，这是模型回答"
	assert response.tool_calls==[]
	assert response.finish_reason=="stop"
	assert response.usage is not None
	assert response.usage.prompt_tokens==10
	assert response.usage.completion_tokens==5
	assert response.usage.total_tokens==15


def test_tool_response()->None:
	response=asyncio.run(
		call_tool_response(
			{
				"id":"call_progress_001",
				"type":"function",
				"function":{
					"name":"get_user_progress",
					"arguments":"{\"user_id\":1}"
				}
			}
		)
	)

	assert response.content is None
	assert response.finish_reason=="tool_calls"
	assert response.usage is None
	assert len(response.tool_calls)==1

	tool_call=response.tool_calls[0]
	assert tool_call.id=="call_progress_001"
	assert tool_call.name=="get_user_progress"
	assert tool_call.arguments=={"user_id":1}