import asyncio
import time
import random

from numpy.random import exponential


class RetryableModelError(Exception):
	# 暂时性模型错误允许重试。
	pass


class NonRetryableModelError(Exception):
	# 永久性模型错误不应重试。
	pass


async def mock_model_call(request_id:int)->str:
	# 模拟模型网络等待。
	await asyncio.sleep(1)
	if request_id==2:
		raise RuntimeError("模型请求失败")
	return f"请求{request_id}完成"


async def run_batch(request_ids:list[int])->list[str|Exception]:
	# 创建批量模型调用协程。
	coroutines=[]
	for request_id in request_ids:
		coroutines.append(mock_model_call(request_id))
	# 保留每个请求的成功值或异常对象。
	return await asyncio.gather(*coroutines,return_exceptions=True)


def split_results(request_ids:list[int],results:list[str|Exception])->tuple[list[dict],list[dict]]:
	# 将批量结果拆分为成功和失败记录。
	success_results=[]
	failed_results=[]
	for request_id,result in zip(request_ids,results):
		if isinstance(result,Exception):
			failed_results.append({"request_id":request_id,"error":str(result)})
			continue
		success_results.append({"request_id":request_id,"content":result})
	return success_results,failed_results


def get_failed_request_ids(failed_results:list[dict])->list[int]:
	# 提取失败任务，供后续定向重试。
	return [failed_result["request_id"] for failed_result in failed_results]


attempt_counts={}


async def mock_model_call_with_retry(request_id:int)->str:
	# 记录调用次数，用于模拟第一次失败、后续成功。
	attempt_counts[request_id]=attempt_counts.get(request_id,0)+1
	await asyncio.sleep(1)
	if request_id==2 and attempt_counts[request_id]==1:
		raise RuntimeError("模型第一次调用失败")
	return f"请求{request_id}完成"


async def call_with_retry(request_id:int,max_retries:int)->str:
	# 执行首次调用和有限次数的额外重试。
	attempt=0
	while attempt<=max_retries:
		try:
			attempt+=1
			return await mock_model_call_with_retry(request_id)
		except Exception:
			if attempt<=max_retries:
				continue
			raise


async def mock_model_call_with_error(request_id:int)->str:
	# 模拟模型网络等待和不同类别的错误。
	await asyncio.sleep(1)
	if request_id==2:
		raise RetryableModelError("模型暂时繁忙")
	if request_id==3:
		raise NonRetryableModelError("请求参数格式错误")
	return f"请求{request_id}完成"

def calculate_backoff(retry_index:int,base_delay:float=0.5,max_delay:float=8.0)->float:
	exponential_delay=base_delay * (2 ** retry_index)
	capped_delay=min(exponential_delay,max_delay)
	return random.uniform(0,capped_delay)

async def call_with_selective_retry(request_id:int,max_retries:int)->str:
	# 只对暂时性模型错误执行有限重试。
	attempt=0
	retry_index=0
	while attempt<max_retries:
		try:
			attempt+=1
			return await mock_model_call_with_error(request_id)
		except RetryableModelError:
			if attempt>max_retries:
				raise
			delay_seconds=calculate_backoff(retry_index)
			print(f"第{attempt}次调用失败,等待{delay_seconds:1f}秒后重试")
			await asyncio.sleep(delay_seconds)
			retry_index+=1
		except NonRetryableModelError:
			raise
		except Exception:
			raise

async def slow_model_call(request_id:int)->str:
	print(f"请求{request_id}开始")
	try:
		await asyncio.sleep(3)
		print(f"请求{request_id}正常完成")
		return f"请求{request_id}完成"
	finally:
		print(f"请求{request_id}结束清理")

async def call_with_timeout(request_id:int,timeout_seconds:float)->str:
	#最多等待指定时间
	return await asyncio.wait_for(
		slow_model_call(request_id),
		timeout=timeout_seconds
	)
async def test_timeout()->None:
	try:
		result=await call_with_timeout(1,2)
		print(result)
	except asyncio.TimeoutError:
		print("外层捕获：模型请求超时")

async def limited_model_call(request_id:int,semaphore:asyncio.Semaphore)->str:
	async with semaphore:
		print(f"请求{request_id}开始")
		await asyncio.sleep(1)
		print(f"请求{request_id}完成")
		return f"请求{request_id}完成"

async def run_limited_batch(request_ids:list[int],max_concurrency:int)->list[str]:
	semaphore=asyncio.Semaphore(max_concurrency)
	coroutines=[]
	for request_id in request_ids:
		coroutines.append(limited_model_call(request_id,semaphore))
	return await asyncio.gather(*coroutines)

async def compare_concurrency()->None:
	for max_concurrency in [1,2,5]:
		start_time=time.perf_counter()
		await run_limited_batch([1,2,3,4,5],max_concurrency)
		elapsed_time=time.perf_counter()-start_time
		print(f"并发上限：{max_concurrency}，耗时：{elapsed_time:.2f}秒")

async def cancellable_model_call()->None:
	print("模型调用开始")
	try:
		await asyncio.sleep(5)
		print("模型调用完成")
	except asyncio.CancelledError:
		print("模型调用收到取消信号")
		raise
	finally:
		print("模型调用清理资源")

async def test_cancellation()->None:
	task=asyncio.create_task(cancellable_model_call())

	await asyncio.sleep(1)

	print("外层取消模型任务")
	task.cancel()

	try:
		await task
	except asyncio.CancelledError:
		print("外层确认任务已取消")

async def cancellable_batch_call(request_id:int)->str:
	print(f"请求{request_id}开始")
	try:
		await asyncio.sleep(5)
		print(f"请求{request_id}完成")
		return f"请求{request_id}完成"
	except asyncio.CancelledError:
		print(f"请求{request_id}收到取消信号")
		raise
	finally:
		print(f"请求{request_id}清理资源")

async def gather_batch(coroutines:list)->list:
	return await asyncio.gather(*coroutines)

async def test_batch_cancellation()->None:
	coroutines=[
		cancellable_batch_call(request_id)
		for request_id in [1,2,3]
	]

	batch_task=asyncio.create_task(
		gather_batch(coroutines)
	)

	await asyncio.sleep(1)

	print("外层取消批量任务")
	batch_task.cancel()

	try:
		await batch_task
	except asyncio.CancelledError:
		print("外层确认批量任务已取消")

async def submit_request(queue:asyncio.Queue[int],request_id:int)->bool:
	try:
		queue.put_nowait(request_id)
		print(f"请求{request_id}进入队列")
		return True
	except asyncio.QueueFull:
		print(f"请求{request_id}被拒绝:队列已满")
		return False

async def consume_requests(queue:asyncio.Queue[int],semaphore:asyncio.Semaphore)->None:
	while True:
		request_id=await queue.get()
		try:
			async with semaphore:
				print(f"请求{request_id}开始执行")
				await asyncio.sleep(1)
				print(f"请求{request_id}结束执行")
		finally:
			queue.task_done()

async def test_queue_limit()->None:
	queue=asyncio.Queue(maxsize=2)
	semaphore=asyncio.Semaphore(2)
	consumer_tasks=[asyncio.create_task(consume_requests(queue,semaphore)) for _ in range(3)]
	for request_id in range(1,6):
		await submit_request(queue,request_id)
	await queue.join()
	for consumer_task in consumer_tasks:
		consumer_task.cancel()

	for consumer_task in consumer_tasks:
		try:
			await consumer_task
		except asyncio.CancelledError:
			pass

	print("所有消费者任务已取消")


async def run_current_experiments()->None:
	# 执行批量并发实验。
	request_ids=[1,2,3]
	start_time=time.perf_counter()
	results=await run_batch(request_ids)
	elapsed_time=time.perf_counter()-start_time
	success_results,failed_results=split_results(request_ids,results)
	failed_request_ids=get_failed_request_ids(failed_results)
	print(f"成功结果：{success_results}")
	print(f"失败结果：{failed_results}")
	print(f"失败请求ID：{failed_request_ids}")
	print(f"批量调用耗时：{elapsed_time:.2f}秒")

	# 执行普通有限重试实验。
	attempt_counts.clear()
	print(f"普通重试结果：{await call_with_retry(2,2)}")

	# 执行选择性重试实验。
	print(f"选择性重试成功：{await call_with_selective_retry(1,2)}")
	try:
		await call_with_selective_retry(2,2)
	except RetryableModelError as error:
		print(f"暂时性错误重试耗尽：{error}")
	try:
		await call_with_selective_retry(3,2)
	except NonRetryableModelError as error:
		print(f"永久性错误立即失败：{error}")
	try:
		timeout_result=await call_with_timeout(1,2)
		print(f"超时测试结果:{timeout_result}")
	except asyncio.TimeoutError:
		print("超时测试：模型请求超时")


	await call_with_selective_retry(2, 2)
if __name__=="__main__":
	#asyncio.run(run_current_experiments())
	#asyncio.run(test_timeout())
	# results = asyncio.run(run_limited_batch([1, 2, 3, 4, 5], 2))
	# print(results)
	#asyncio.run(compare_concurrency())
	#asyncio.run(test_cancellation())
	#asyncio.run(test_batch_cancellation())
	asyncio.run(test_queue_limit())