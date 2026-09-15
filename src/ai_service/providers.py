from abc import ABC,abstractmethod

import httpx

from .config import Settings


class ModelProviderError(Exception):
	pass


class ModelUpstreamError(ModelProviderError):
	pass


class ModelProvider(ABC):
	def __init__(self,settings:Settings,http_client:httpx.AsyncClient)->None:
		self.settings=settings
		self.http_client=http_client

	@abstractmethod
	def supports(self,model_name:str)->bool:
		raise NotImplementedError

	@abstractmethod
	async def chat(self,model_name:str,messages:list[dict],temperature:float)->str:
		raise NotImplementedError


class MockProvider(ModelProvider):
	def supports(self,model_name:str)->bool:
		return model_name=="mock-model"

	async def chat(self,model_name:str,messages:list[dict],temperature:float)->str:
		return (
			f"模型={model_name},"
			f"收到{len(messages)}条消息,"
			f"temperature={temperature}"
		)


def build_payload(model_name:str,messages:list[dict],temperature:float)->dict:
	return {
		"model":model_name,
		"messages":messages,
		"temperature":temperature,
		"stream":False
	}


class OpenAICompatibleProvider(ModelProvider):
	def supports(self,model_name:str)->bool:
		return bool(model_name)

	async def chat(self,model_name:str,messages:list[dict],temperature:float)->str:
		if not self.settings.base_url:
			raise ModelProviderError("模型 Provider 缺少 MODEL_BASE_URL")
		url=f"{self.settings.base_url.rstrip('/')}/v1/chat/completions"
		headers={
			"Authorization":f"Bearer {self.settings.api_key}",
			"Content-Type":"application/json"
		}
		try:
			response=await self.http_client.post(
			url,
			headers=headers,
			json=build_payload(model_name,messages,temperature)
			)
		except httpx.RequestError as error:
			raise ModelUpstreamError("模型上游网络请求失败") from error
		if response.status_code>=400:
			raise ModelUpstreamError(
				f"模型上游请求失败，状态码：{response.status_code}"
			)
		try:
			data=response.json()
			return data["choices"][0]["message"]["content"]
		except (ValueError,KeyError,IndexError,TypeError) as error:
			raise ModelUpstreamError("模型响应格式无效") from error


def create_provider(provider_name:str,settings:Settings,http_client:httpx.AsyncClient)->ModelProvider:
	if provider_name=="mock":
		return MockProvider(settings,http_client)
	if provider_name in {"deepseek","openai"}:
		return OpenAICompatibleProvider(settings,http_client)
	raise ValueError(f"不支持的模型供应商:{provider_name}")
