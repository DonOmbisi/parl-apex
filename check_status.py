# check_status.py — only polls, never creates
import os
from dotenv import load_dotenv
load_dotenv()
from valyu import Valyu

valyu = Valyu(os.environ["VALYU_API_KEY"])

# Check the first task only
result = valyu.deepresearch.status("de2474f0-0036-43cd-8995-3d2910b4e735")
print(f"Status: {result.status}")
print(f"Progress: {result.progress.current_step}/{result.progress.total_steps}")
print(f"Output: {'READY' if result.output else 'Not yet'}")