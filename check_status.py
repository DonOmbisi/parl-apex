"""check_status.py — poll the status of a Valyu deep-research task.
Never creates a new task.

Usage:
    uv run python check_status.py <deepresearch_id>

If no argument is given, prints usage and exits.
"""
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from valyu import Valyu

if len(sys.argv) < 2:
    print("Usage: uv run python check_status.py <deepresearch_id>")
    print("\nExample:")
    print("  uv run python check_status.py de2474f0-0036-43cd-8995-3d2910b4e735")
    sys.exit(1)

task_id = sys.argv[1]
valyu = Valyu(os.environ["VALYU_API_KEY"])
result = valyu.deepresearch.status(task_id)

# Progress (not always present on all SDK versions)
progress = getattr(result, "progress", None)
if progress:
    current = getattr(progress, "current_step", "?")
    total   = getattr(progress, "total_steps", "?")
    print(f"Progress : {current}/{total}")
else:
    print("Progress : (not available)")

print(f"Status   : {result.status}")
print(f"Output   : {'READY — run process_tenders.py' if result.output else 'Not yet ready'}")

if result.output:
    print(f"\nProcess with:")
    print(f"  uv run python process_tenders.py {task_id}")