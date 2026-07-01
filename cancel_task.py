import os
from dotenv import load_dotenv
load_dotenv()
from valyu import Valyu

valyu = Valyu(os.environ["VALYU_API_KEY"])
result = valyu.deepresearch.cancel("2b597244-ec6f-4ef5-8f44-72668387d07b")
print("Cancelled:", result)