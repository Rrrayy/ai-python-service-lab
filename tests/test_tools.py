import asyncio
import json

from src.ai_service.providers import ToolCall
from src.ai_service.tools import execute_tool_call,execute_tool_calls,tool_registry


def call(
	call_id:str="call_001",
	name:str="get_user_progress",
	arguments:dict|None=None
)->ToolCall:
	return ToolCall(
		id=call_id,
		name=name,
		arguments=arguments if arguments is not None else {"user_id":1}
	)


def read_content(result:dict)->dict:
	return json.loads(result["content"])


def test_success()->None:
	result=asyncio.run(execute_tool_call(call(),tool_registry,is_authenticated=True))

	assert result["role"]=="tool"
	assert result["tool_call_id"]=="call_001"
	assert read_content(result)=={
		"user_id":1,
		"topic":"Agent",
		"completed":12
	}


def test_invalid_arguments()->None:
	result=asyncio.run(execute_tool_call(
		call(arguments={"user_id":"abc"}),tool_registry,is_authenticated=True
	))

	assert read_content(result)["error_code"]=="INVALID_TOOL_ARGUMENTS"


def test_unknown_tool()->None:
	result=asyncio.run(execute_tool_call(
		call(name="unknown_tool"),tool_registry,is_authenticated=True
	))

	assert read_content(result)["error_code"]=="TOOL_NOT_FOUND"


def test_unauthorized_tool()->None:
	result=asyncio.run(execute_tool_call(
		call(),tool_registry,is_authenticated=False
	))

	assert read_content(result)["error_code"]=="TOOL_UNAUTHORIZED"


def test_timeout()->None:
	result=asyncio.run(execute_tool_call(
		call(name="slow_tool",arguments={}),tool_registry,is_authenticated=True
	))

	assert read_content(result)["error_code"]=="TOOL_TIMEOUT"


def test_execution_failure()->None:
	result=asyncio.run(execute_tool_call(
		call(name="failing_tool",arguments={}),tool_registry,is_authenticated=True
	))

	assert read_content(result)["error_code"]=="TOOL_EXECUTION_FAILED"


def test_multiple_calls_keep_ids()->None:
	results=asyncio.run(execute_tool_calls(
		[call("call_001"),call("call_002")],
		tool_registry,
		is_authenticated=True
	))

	assert [result["tool_call_id"] for result in results]==[
		"call_001",
		"call_002"
	]
	assert all(read_content(result)["completed"]==12 for result in results)
