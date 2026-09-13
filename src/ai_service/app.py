import asyncio

from fastapi import Depends,FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field


DEFAULT_MODEL="mock_model"


class ChatMessage(BaseModel):
	role:str
	content:str


class ChatRequest(BaseModel):
	model:str
	messages:list[ChatMessage]
	temperature:float=Field(default=0.7,ge=0,le=2)


class ChatResponse(BaseModel):
	model:str
	content:str
	success:bool=True
	error:str|None=None


class ApiError(Exception):
	def __init__(self,status_code:int,code:str,message:str):
		super().__init__(message)
		self.status_code=status_code
		self.code=code
		self.message=message


app=FastAPI()


def get_model_name()->str:
	return DEFAULT_MODEL


@app.exception_handler(ApiError)
async def handle_api_error(request:Request,error:ApiError):
	return JSONResponse(
		status_code=error.status_code,
		content={
			"code":error.code,
			"message":error.message
		}
	)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request:Request,error:RequestValidationError):
	details=[]
	for item in error.errors():
		details.append({
			"location":list(item["loc"]),
			"type":item["type"],
			"message":item["msg"]
		})
	return JSONResponse(
		status_code=422,
		content={
			"code":"REQUEST_VALIDATION_ERROR",
			"message":"请求参数校验失败",
			"details":details
		}
	)


@app.get("/health")
async def health():
	return {"status":"ok"}


@app.get("/users")
async def list_users(page:int=1,page_size:int=20):
	return {
		"page":page,
		"page_size":page_size
	}


@app.get("/users/{user_id}")
async def get_user(user_id:int):
	return {
		"user_id":user_id,
		"message":"查询客户成功"
	}


@app.post("/v1/chat/completions",response_model=ChatResponse)
async def chat(request:ChatRequest):
	return ChatResponse(
		model=request.model,
		content=f"收到{len(request.messages)}条消息"
	)


@app.get("/model")
async def model(model_name:str=Depends(get_model_name)):
	return {"model":model_name}


@app.get("/model/{model_name}")
async def get_model(model_name:str):
	if model_name!=DEFAULT_MODEL:
		raise ApiError(404,"MODEL_NOT_FOUND","模型不存在")
	return {"model":model_name}


async def slow_model()->str:
	await asyncio.sleep(3)
	return "模型响应"


@app.get("/debug/timeout")
async def debug_timeout():
	try:
		result=await asyncio.wait_for(slow_model(),timeout=1)
		return {"content":result}
	except asyncio.TimeoutError as error:
		raise ApiError(504,"MODEL_TIMEOUT","模型调用超时") from error
