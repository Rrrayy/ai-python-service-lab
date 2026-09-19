import httpx
import json
from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from abc import ABC,abstractmethod


class ProviderError(Exception):
	pass


class ProviderTimeoutError(ProviderError):
	pass


class ProviderAuthenticationError(ProviderError):
	pass


class ProviderRateLimitError(ProviderError):
	pass


class ProviderUpstreamError(ProviderError):
	pass


class ProviderProtocolError(ProviderError):
	pass



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
	def parse_tool_calls(self, data: Any) -> list[ToolCall]:
		if not isinstance(data, list):
			raise ProviderProtocolError("tool_calls格式错误")

		tool_calls = []
		for item in data:
			if not isinstance(item, dict):
				raise ProviderProtocolError("工具调用格式错误")

			call_id = item.get("id")
			if not isinstance(call_id, str) or not call_id:
				raise ProviderProtocolError("工具调用id缺失")

			function_data = item.get("function")
			if not isinstance(function_data, dict):
				raise ProviderProtocolError("工具function格式错误")

			name = function_data.get("name")
			if not isinstance(name, str) or not name:
				raise ProviderProtocolError("工具名称缺失")

			arguments_text = function_data.get("arguments")
			if not isinstance(arguments_text, str):
				raise ProviderProtocolError("工具arguments必须是JSON字符串")

			try:
				arguments = json.loads(arguments_text)
			except json.JSONDecodeError as error:
				raise ProviderProtocolError("工具arguments不是合法JSON") from error

			if not isinstance(arguments, dict):
				raise ProviderProtocolError("工具arguments必须是对象")

			tool_calls.append(
				ToolCall(
					id=call_id,
					name=name,
					arguments=arguments
				)
			)

		return tool_calls

	def parse_response(self, data: dict[str, Any]) -> ModelResponse:
		if not isinstance(data, dict):
			raise ProviderProtocolError("模型响应必须是JSON对象")

		choices = data.get("choices")
		if not isinstance(choices, list) or not choices:
			raise ProviderProtocolError("模型响应缺少choices")

		choice = choices[0]
		if not isinstance(choice, dict):
			raise ProviderProtocolError("模型响应choice格式错误")

		message = choice.get("message")
		if not isinstance(message, dict):
			raise ProviderProtocolError("模型响应缺少message")

		usage_data = data.get("usage")
		usage = None
		if usage_data is not None:
			if not isinstance(usage_data, dict):
				raise ProviderProtocolError("模型响应usage格式错误")

			try:
				usage = TokenUsage.model_validate(usage_data)
			except ValidationError as error:
				raise ProviderProtocolError("模型响应usage字段不合法") from error

		tool_calls = self.parse_tool_calls(message.get("tool_calls", []))

		try:
			return ModelResponse(
				content=message.get("content"),
				tool_calls=tool_calls,
				finish_reason=choice.get("finish_reason"),
				usage=usage
			)
		except ValidationError as error:
			raise ProviderProtocolError("模型响应字段不合法") from error

	async def chat(self, request: ModelRequest) -> ModelResponse:
		payload = self.build_payload(request)
		url = f"{self.base_url}/v1/chat/completions"
		headers = {
			"Authorization": f"Bearer {self.api_key}",
			"Content-Type": "application/json"
		}

		try:
			response = await self.http_client.post(
				url,
				headers=headers,
				json=payload
			)
		except httpx.TimeoutException as error:
			raise ProviderTimeoutError("模型请求超时") from error
		except httpx.RequestError as error:
			raise ProviderUpstreamError("模型网络请求失败") from error

		try:
			response.raise_for_status()
		except httpx.HTTPStatusError as error:
			status_code = error.response.status_code
			if status_code in {401, 403}:
				raise ProviderAuthenticationError("模型认证失败") from error
			if status_code == 429:
				raise ProviderRateLimitError("模型请求受到限流") from error
			raise ProviderUpstreamError(
				f"模型上游返回HTTP {status_code}"
			) from error

		try:
			response_data = response.json()
		except (json.JSONDecodeError, ValueError) as error:
			raise ProviderProtocolError("模型响应不是合法JSON") from error

		return self.parse_response(response_data)

