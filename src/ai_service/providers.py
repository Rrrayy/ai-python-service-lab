import httpx
import json
from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,Field
from abc import ABC,abstractmethod

class Message(BaseModel):
	model_config = ConfigDict(extra="forbid")
	role:Literal["system","user","assistant","tool"]
	content:str|None=None
	tool_calls:list[dict[str,Any]]=Field(default_factory=list)
	tool_call_id:str|None=None

class ToolCall(BaseModel):
	model_config = ConfigDict(extra="forbid")
	id:str
	name:str
	arguments:dict[str,Any]

class ToolDefinition(BaseModel):
	model_config = ConfigDict(extra="forbid")
	name:str
	description:str
	parameters:dict[str,Any]

class TokenUsage(BaseModel):
	model_config = ConfigDict(extra="forbid")
	prompt_tokens:int=Field(ge=0)
	completion_tokens: int = Field(ge=0)
	total_tokens: int = Field(ge=0)

class ModelRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")
	model:str
	messages:list[Message]
	tools: list[ToolDefinition] = Field(default_factory=list)
	temperature: float = Field(ge=0)
	stream: bool = False

class ModelResponse(BaseModel):
	model_config=ConfigDict(extra="forbid")
	content:str|None=None
	tool_calls:list[ToolCall]=Field(default_factory=list)
	finish_reason:str|None=None
	usage:TokenUsage|None=None

class ModelProvider(ABC):
	@abstractmethod
	async def chat(self,request:ModelRequest)->ModelResponse:
		raise NotImplementedError


class MockProvider(ModelProvider):
	async def chat(self,request:ModelRequest)->ModelResponse:
		return ModelResponse(
			content=f"收到{len(request.messages)}条消息",
			finish_reason="stop"
		)

class OpenAICompatibleProvider(ModelProvider):

	def __init__(
			self,
			base_url: str,
			api_key: str,
			http_client: httpx.AsyncClient
	) -> None:
		self.base_url = base_url.rstrip("/")
		self.api_key = api_key
		self.http_client = http_client

	def build_payload(self,request:ModelRequest)->dict[str,Any]:
		payload={
			"model":request.model,
			"messages":[
				message.model_dump(exclude_none=True)
				for message in request.messages
			],
			"temperature":request.temperature,
			"stream":request.stream
		}
		if request.tools:
			payload["tools"]=[
				{
					"type":"function",
					"function":tool.model_dump()
				}
				for tool in request.tools
			]
		return payload

	# {
	# 	"choices": [
	# 		{
	# 			"message": {
	# 				"role": "assistant",
	# 				"content": "你好",
	# 				"tool_calls":[
				# 		{
				# 			"id":"call_progress_001",
				# 			"type":"function",
				# 			"function":{
				# 				"name":"get_user_progress",
				# 				"arguments":"{\"user_id\":1}"
				# 			}
				# 		}
				# 	]
	# 			},
	# 			"finish_reason": "stop"
	# 		}
	# 	],
	# 	"usage": {
	# 		"prompt_tokens": 10,
	# 		"completion_tokens": 5,
	# 		"total_tokens": 15
	# 	}
	# }
	def parse_response(self,data:dict[str,Any])->ModelResponse:
		choices=data.get("choices")
		if not isinstance(choices,list) or not choices:
			raise ValueError("模型响应缺少choices")

		choice=choices[0]
		if not isinstance(choice,dict):
			raise ValueError("模型响应choice格式错误")

		message=choice.get("message")
		if not isinstance(message,dict):
			raise ValueError("模型响应缺少message")

		usage_data=data.get("usage")
		usage=None
		if isinstance(usage_data,dict):
			usage=TokenUsage.model_validate(usage_data)

		tool_calls_data = message.get("tool_calls", [])
		tool_calls = self.parse_tool_calls(tool_calls_data)

		return ModelResponse(
			content=message.get("content"),
			tool_calls=tool_calls,
			finish_reason=choice.get("finish_reason"),
			usage=usage
		)

	def parse_tool_calls(self, data: Any) -> list[ToolCall]:
		if not isinstance(data, list):
			raise ValueError("tool_calls格式错误")

		tool_calls = []
		for item in data:
			if not isinstance(item, dict):
				raise ValueError("工具调用格式错误")

			call_id = item.get("id")
			if not isinstance(call_id, str) or not call_id:
				raise ValueError("工具调用id缺失")

			function_data = item.get("function")
			if not isinstance(function_data, dict):
				raise ValueError("工具function格式错误")

			name = function_data.get("name")
			if not isinstance(name, str) or not name:
				raise ValueError("工具名称缺失")

			arguments_text = function_data.get("arguments")
			if not isinstance(arguments_text, str):
				raise ValueError("工具arguments必须是JSON字符串")

			try:
				arguments = json.loads(arguments_text)
			except json.JSONDecodeError as error:
				raise ValueError("工具arguments不是合法JSON") from error

			if not isinstance(arguments, dict):
				raise ValueError("工具arguments必须是对象")

			tool_calls.append(
				ToolCall(
					id=call_id,
					name=name,
					arguments=arguments
				)
			)

		return tool_calls

	async def chat(self, request: ModelRequest) -> ModelResponse:
		payload = self.build_payload(request)
		url = f"{self.base_url}/v1/chat/completions"
		headers = {
			"Authorization": f"Bearer {self.api_key}",
			"Content-Type": "application/json"
		}
		response = await self.http_client.post(
			url,
			headers=headers,
			json=payload
		)
		response.raise_for_status()
		return self.parse_response(response.json())


async def main()->None:

	async def mock_handler(request:httpx.Request)->httpx.Response:
		print(request.method)
		print(request.url)
		print(request.headers["authorization"])
		payload = json.loads(request.content.decode("utf-8"))
		print(payload)
		return httpx.Response(
			200,
			json={
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
			}
		)

	transport=httpx.MockTransport(mock_handler)

	async with httpx.AsyncClient(transport=transport) as http_client:
		provider=OpenAICompatibleProvider(
			base_url="https://example.com",
			api_key="test-key",
			http_client=http_client
		)
		request=ModelRequest(
			model="mock-model",
			messages=[
				Message(
					role="user",
					content="你好"
				)
			],
			temperature=0.7
		)
		response=await provider.chat(request)
		print(response.model_dump())


if __name__=="__main__":
	import asyncio
	asyncio.run(main())
