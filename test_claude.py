import anthropic
from dotenv import load_dotenv
import os

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=64,
    messages=[
        {"role": "user", "content": "Reply with: AGENT ONLINE"}
    ]
)

print(response.content[0].text)