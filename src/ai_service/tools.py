import json
import asyncio

from pydantic import BaseModel,Field,ConfigDict,ValidationError


class UserProgressArguments(BaseModel):
	model_config = ConfigDict(strict=True,extra="forbid")
	user_id:int=Field(ge=1)

class EmptyArguments(BaseModel):
	model_config=ConfigDict(strict=True,extra="forbid")

class ToolExecutionError(Exception):
	pass

async def get_user_progress(user_id:int)->dict:
	return{
		"user_id":user_id,
		"topic":"Agent",
		"completed":12
	}

async def slow_tool()->dict:
	print("慢工具开始")
	try:
		await asyncio.sleep(5)
		print("慢工具完成")
		return {"status":"finished"}
	finally:
		print("慢工具清理资源")

async def failing_tool()->dict:
	raise ToolExecutionError("用户进度服务暂时不可用")

tool_definition={
	"name":"get_user_progress",
	"description":"查询用户已完成的学习主题和任务数量",
	"parameters":{
		"type":"object",
		"properties":{
			"user_id":{
				"type":"integer",
				"minimum":1
			}
		},
		"required":["user_id"],
		"additionalProperties":False
	},
	"argument_model":UserProgressArguments,
	"handler":get_user_progress,
	"timeout":3.0,
	"requires_auth":True
}

slow_tool_definition={
	"name":"slow_tool",
	"description":"用于测试工具超时",
	"parameters":{
		"type":"object",
		"properties":{},
		"required":[],
		"additionalProperties":False
	},
	"argument_model":EmptyArguments,
	"handler":slow_tool,
	"timeout":1.0,
	"requires_auth":False
}

failing_tool_definition={
	"name":"failing_tool",
	"description":"用于测试工具业务失败",
	"parameters":{
		'type':"object",
		"properties":{},
		"required":[],
		"additionalProperties":False
	},
	"argument_model":EmptyArguments,
	"handler":failing_tool,
	"timeout":3.0,
	"requires_auth":False
}

tool_registry={
	"get_user_progress":tool_definition,
	"slow_tool":slow_tool_definition,
	"failing_tool":failing_tool_definition
}

assistant_tool_calls=[
	{
		"id":"call_progress_001",
		"type":"function",
		"function":{
			"name":"get_user_progress",
			"arguments":'{"user_id":1}'
		}
	},
	{
		"id": "call_progress_002",
		"type": "function",
		"function": {
			"name": "get_user_progress",
			"arguments": '{"user_id":"abc"}'
		}
	}
]

def tool_error(tool_call_id:str,error_code:str,message:str)->dict:
	return {
		"role":"tool",
		"tool_call_id":tool_call_id,
		"content":json.dumps({
			"ok":False,
			"error_code":error_code,
			"error":message
		},ensure_ascii=False)
	}

async def execute_tool_call(tool_call:dict,tool_registry:dict,is_authenticated:bool)->dict:
	name=tool_call["function"]["name"]
	call_id=tool_call["id"]
	if name not in tool_registry:
		return tool_error(call_id, "TOOL_NOT_FOUND", f"工具 {name} 不存在")
	tool_definition=tool_registry[name]
	if tool_definition["requires_auth"] and not is_authenticated:
		return	tool_error(call_id,"TOOL_UNAUTHORIZED","调用工具需要认证")

	argument_model = tool_registry[name]["argument_model"]
	try:
		arguments=json.loads(tool_call["function"]["arguments"])
	except json.JSONDecodeError:
		return tool_error(call_id,"INVALID_TOOL_ARGUMENTS","arguments不是合法JSON")
	if not isinstance(arguments, dict):
		return tool_error(call_id,"INVALID_TOOL_ARGUMENTS","arguments解析后必须是对象")
	try:
		validated=argument_model.model_validate(arguments)
	except ValidationError :
		return tool_error(call_id,"INVALID_TOOL_ARGUMENTS","arguments参数不合法")

	handler=tool_registry[name]["handler"]
	timeout=tool_registry[name]["timeout"]
	try:
		result=await asyncio.wait_for(
			handler(**validated.model_dump()),
			timeout=timeout
		)
	except asyncio.TimeoutError:
		return tool_error(call_id,"TOOL_TIMEOUT","工具执行超时")
	except ToolExecutionError as error:
		return tool_error(call_id,"TOOL_EXECUTION_FAILED",str(error))
	return {
		"role":"tool",
		"tool_call_id":tool_call["id"],
		"content":json.dumps(result,ensure_ascii=False)
	}

async def execute_tool_calls(tool_calls:list[dict],tool_registry:dict,is_authenticated:bool)->list[dict]:
	coroutines=[]
	for tool_call in tool_calls:
		coroutine=execute_tool_call(tool_call,tool_registry,is_authenticated)
		coroutines.append(coroutine)
	return await asyncio.gather(*coroutines)

async def main()->None:
	results=await execute_tool_calls(assistant_tool_calls,tool_registry,is_authenticated=True)
	for result in results:
		print(result)

if __name__=="__main__":
	import asyncio
	asyncio.run(main())