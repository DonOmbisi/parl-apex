"""create_tender_task.py — create one Valyu deep-research task and print
the task ID. Run this ONCE per research cycle; do not run again until
the previous task has completed or been cancelled.

Usage:
    uv run python create_tender_task.py
"""
import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

from connectors.valyu_tender_connector import create_tender_research_task

WEBHOOK_URL = "https://parl-apex.onrender.com/webhooks/valyu/tender-research"


async def main() -> None:
    print("Creating Valyu deep-research task (mode=standard — takes 15-25 min)…")
    task_id = await create_tender_research_task(webhook_url=WEBHOOK_URL)
    if task_id:
        print(f"\n✅ Task created: {task_id}")
        print(f"\nCheck status with:\n  uv run python check_status.py {task_id}")
        print(f"\nProcess results with:\n  uv run python process_tenders.py {task_id}")
    else:
        print("❌ Task creation returned an empty ID — check the connector logs.")


asyncio.run(main())
