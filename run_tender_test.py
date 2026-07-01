# run_tender_test.py — delete after testing
import asyncio
import httpx, os
from dotenv import load_dotenv
load_dotenv()

from valyu import Valyu

valyu = Valyu(os.environ["VALYU_API_KEY"])
status = valyu.deepresearch.status("de2474f0-0036-43cd-8995-3d2910b4e735")
print("Status:", status)

key = os.environ.get("VALYU_API_KEY", "NOT SET")
print("Key starts with:", key[:8] if len(key) > 8 else key)

from connectors.valyu_tender_connector import create_tender_research_task

async def main():
    task_id = await create_tender_research_task(
        webhook_url="https://parl-apex.onrender.com/webhooks/valyu/tender-research"
    )
    print("Task created:", task_id)

asyncio.run(main())