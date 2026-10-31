import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("GROQ_API_KEY not found in .env")

client = Groq(api_key=api_key)

try:
    models = client.models.list()

    print("\nAvailable Groq Models:\n")
    print("-" * 80)

    for model in models.data:
        print(f"Model ID : {model.id}")
        print(f"Owned By : {model.owned_by}")
        print(f"Created  : {model.created}")
        print("-" * 80)

except Exception as e:
    print(f"Error fetching models: {e}")