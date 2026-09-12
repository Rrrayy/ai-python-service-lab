import pytest
import asyncio

from src.ai_service.async_basics import TaskRecord,TaskStatus,update_task_status
from src.ai_service.async_basics import split_results
from src.ai_service.async_basics import attempt_counts,call_with_retry
from src.ai_service.async_basics import call_with_timeout
from src.ai_service.async_basics import submit_request

def test_invalid_status():
	task=TaskRecord(task_id=1)

	with pytest.raises(ValueError):
		update_task_status(task,TaskStatus.RUNNING)

def test_split_results():
	request_ids=[1,2,3]
	results=[
		"请求1完成",
		RuntimeError("模型请求失败"),
		"请求3完成"
	]

	success_results,failed_results=split_results(request_ids,results)

	assert success_results==[
		{"request_id":1,"content":"请求1完成"},
		{"request_id":3,"content":"请求3完成"}
	]
	assert failed_results==[
		{"request_id":2,"error":"模型请求失败"}
	]

def test_retry_success():
	attempt_counts.clear()

	result=asyncio.run(call_with_retry(2,2))

	assert result=="请求2完成"
	assert attempt_counts[2]==2

def test_timeout():
	with pytest.raises(asyncio.TimeoutError):
		asyncio.run(call_with_timeout(1,2))

def test_queue_full():
	async def run_test():
		queue=asyncio.Queue(maxsize=1)

		first_result=await submit_request(queue,1)
		second_result=await submit_request(queue,2)

		return first_result,second_result

	first_result,second_result=asyncio.run(run_test())

	assert first_result is True
	assert second_result is False