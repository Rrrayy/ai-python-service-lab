from pydantic import Field
from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):
	provider:str=Field(default="mock",validation_alias="MODEL_PROVIDER")
	model_name:str=Field(default="mock-model",validation_alias="MODEL_NAME")
	api_key:str|None=Field(default=None,validation_alias="MODEL_API_KEY")
	base_url:str|None=Field(default=None,validation_alias="MODEL_BASE_URL")
	timeout:float=Field(default=10.0,gt=0,validation_alias="MODEL_TIMEOUT")
	model_config=SettingsConfigDict(extra="ignore")

def validate_settings(settings:Settings)->None:
	if settings.provider=="mock":
		return
	if not settings.api_key:
		raise RuntimeError("真实模型必须配置 MODEL_API_KEY")
	if not settings.base_url:
		raise RuntimeError("真实模型必须配置 MODEL_BASE_URL")
