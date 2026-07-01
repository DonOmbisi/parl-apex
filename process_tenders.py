import os, json
from dotenv import load_dotenv
load_dotenv()
from valyu import Valyu

valyu = Valyu(os.environ["VALYU_API_KEY"])
result = valyu.deepresearch.status("de2474f0-0036-43cd-8995-3d2910b4e735")

output = result.output
print("Output type:", type(output))
print("Raw output preview:")
print(str(output)[:2000])

# Save full output for inspection
with open("tender_result.json", "w", encoding="utf-8") as f:
    if isinstance(output, dict):
        json.dump(output, f, indent=2, ensure_ascii=False)
    elif isinstance(output, list):
        json.dump(output, f, indent=2, ensure_ascii=False)
    else:
        json.dump({"raw": str(output)}, f, indent=2, ensure_ascii=False)

print("\nFull output saved to tender_result.json")

# Count tenders if structured correctly
if isinstance(output, dict):
    tenders = output.get("tenders", [])
    print(f"\nTenders found: {len(tenders)}")
    for t in tenders[:5]:
        print(f"  - {t.get('title', 'NO TITLE')} | {t.get('deadline', 'NO DEADLINE')} | Score-ready: {'description' in t}")
elif isinstance(output, list):
    print(f"\nTenders found (list format): {len(output)}")
    for t in output[:5]:
        print(f"  - {t.get('title', 'NO TITLE')} | {t.get('deadline', 'NO DEADLINE')}")