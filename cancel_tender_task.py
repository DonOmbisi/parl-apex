"""cancel_tender_task.py — cancel a running Valyu deep-research task.

Usage:
    uv run python cancel_tender_task.py <deepresearch_id>
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from valyu import Valyu

if len(sys.argv) < 2:
    print("Usage: uv run python cancel_tender_task.py <deepresearch_id>")
    sys.exit(1)

task_id = sys.argv[1]
valyu = Valyu(os.environ["VALYU_API_KEY"])

try:
    result = valyu.deepresearch.cancel(task_id)
    print("Cancel result:", result)
except Exception as e:
    print(f"Failed to cancel task {task_id}: {e}")
