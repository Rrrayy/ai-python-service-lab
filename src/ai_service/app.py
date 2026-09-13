import asyncio
import json
import re
import time
import uuid
from contextlib import asynccontextmanager

import httpx
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

REQUEST_ID_PATTERN=re.compile(r"^[A-Za-z0-9._-]{1,64}$")

def new_request_id()->str:
	return uuid.uuid4().hex

def resolve_request_id(request:Request)->str:
	client_request_id=request.headers.get("X-Request-ID")
	if client_request_id is not None and REQUEST_ID_PATTERN.fullmatch(client_request_id):
		return client_request_id
	return new_request_id()

def resolve_trace_id(request:Request,request_id:str)->str:
	client_trace_id=request.headers.get("X-Trace-ID")
	if client_trace_id is not None and REQUEST_ID_PATTERN.fullmatch(client_trace_id):
		return client_trace_id
	return request_id

def get_request_id(request:Request)->str:
	return request.state.request_id

def get_model_client(request:Request)->httpx.AsyncClient:
	return request.app.state.model_client

@asynccontextmanager
async def lifespan(app:FastAPI):
	app.state.model_client=httpx.AsyncClient(timeout=10.0)
	print("服务启动：模型客户端已创建")
	try:
		yield
	finally:
		await app.state.model_client.aclose()
		print("服务关闭：模型客户端已释放")

app=FastAPI(lifespan=lifespan)

@app.middleware("http")
async def track_request(request:Request,call_next):
	request_id=resolve_request_id(request)
	trace_id=resolve_trace_id(request,request_id)
	request.state.request_id=request_id
	request.state.trace_id=trace_id
	start_time=time.perf_counter()
	response=None
	try:
		response=await call_next(request)
		return response
	finally:
		elapsed_ms=(time.perf_counter()-start_time)*1000
		status_code=response.status_code if response is not None else 500
		if response is not None:
			response.headers["X-Process-Time"]=f"{elapsed_ms:.2f}"
			response.headers["X-Request-ID"]=request_id
			response.headers["X-Trace-ID"]=trace_id
		access_log={
			"request_id":request_id,
			"trace_id":trace_id,
			"method":request.method,
			"path":request.url.path,
			"status_code":status_code,
			"elapsed_ms":round(elapsed_ms,2)
		}
		print(json.dumps(access_log,ensure_ascii=False))

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

@app.get("/debug/request-id")
async def debug_request_id(request_id:str=Depends(get_request_id)):
	return {"request_id":request_id}

@app.get("/debug/model-client")
async def debug_model_client(model_client:httpx.AsyncClient=Depends(get_model_client)):
	return {
		"client_id":id(model_client),
		"is_closed":model_client.is_closed
	}
