import json
import asyncio
from collections.abc import AsyncIterator
from .agent_loop import ScriptedProvider,run_agent
from typing import Any


def format_sse_event(
		event_name:str,
		data:dict[str,Any],
	)->str:

	#将一个结构化事件转换成 SSE 文本。
	return (
		f"event: {event_name}\n"
		f"data: {json.dumps(data,ensure_ascii=False)}\n"
		"\n"
	)

async def enqueue_event(
		event_queue:asyncio.Queue[dict[str,Any]],
		event:dict[str,Any],
	)->None:
	await event_queue.put(event)

async def event_stream(
	event_queue:asyncio.Queue[dict[str,Any]],
)->AsyncIterator[str]:
	while True:
		event=await event_queue.get()

		if event["event"]=="stream_finished":
			break

		yield format_sse_event(
			event["event"],
			event["data"]
		)

async def run_agent_to_queue(
		event_queue:asyncio.Queue[dict[str,Any]],
)->tuple[str,list[dict]]:
	async def on_event(event:dict[str,Any])->None:
		await enqueue_event(
			event_queue,
			event
		)

	try:
		provider=ScriptedProvider()

		return await run_agent(
			provider=provider,
			user_content="我目前完成了多少个 Agent 学习任务？",
			max_model_calls=3,
			on_event=on_event
		)
	finally:
		await enqueue_event(
			event_queue,
			{
				"event":"stream_finished",
				"data":{}
			}
		)


async def test_event_bridge()->None:
	event_queue:asyncio.Queue[dict[str,Any]]=asyncio.Queue()

	agent_task=asyncio.create_task(
		run_agent_to_queue(event_queue)
	)

	async for event_text in event_stream(event_queue):
		print(repr(event_text))

	final_content,messages=await agent_task

	print(f"最终回答：{final_content}")
	print(f"消息数量：{len(messages)}")

if __name__=="__main__":
	asyncio.run(test_event_bridge())