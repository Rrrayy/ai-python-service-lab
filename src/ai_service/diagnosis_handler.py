from typing import Any

from .diagnosis_service import diagnose_issue
from .providers import ModelProvider
from .response import (
	build_exception_response,
	build_success_response,
)


async def handle_diagnosis(
	provider:ModelProvider,
	user_content:str,
	request_id:str,
	max_model_calls:int=3,
)->dict[str,Any]:
	try:
		report=await diagnose_issue(
			provider=provider,
			user_content=user_content,
			max_model_calls=max_model_calls,
		)
	except Exception as error:
		return build_exception_response(
			error,
			request_id,
		)

	return build_success_response(
		report,
		request_id,
	)

async def main()->None:
	from .providers import MockProvider

	provider=MockProvider()

	result=await handle_diagnosis(
		provider=provider,
		user_content="分析数据库连接池耗尽问题",
		request_id="req-handler-001",
	)

	print(result)


if __name__=="__main__":
	import asyncio

	asyncio.run(main())