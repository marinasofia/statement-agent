import anthropic
import os
import logging
import re
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from core.config import CLAUDE_MODEL, CLAUDE_MAX_TOKENS, CLAUDE_MAX_RETRIES, CLAUDE_RETRY_MIN_WAIT, CLAUDE_RETRY_MAX_WAIT

load_dotenv()
logger = logging.getLogger(__name__)

_client = None

def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in .env")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client

@retry(
    retry=retry_if_exception_type((anthropic.APIStatusError, anthropic.APIConnectionError)),
    stop=stop_after_attempt(CLAUDE_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=CLAUDE_RETRY_MIN_WAIT, max=CLAUDE_RETRY_MAX_WAIT),
    reraise=True
)
def call_claude(system_prompt: str, user_message: str, max_tokens: int = CLAUDE_MAX_TOKENS) -> str:
    try:
        client = get_client()
        logger.info(f"Calling Claude ({len(user_message)} chars)")

        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )

        if not message.content:
            raise ValueError("Claude returned empty response")

        return message.content[0].text

    except anthropic.APIStatusError as e:
        logger.warning(f"Claude API status error (will retry): {e.status_code} — {e.message}")
        raise
    except anthropic.APIConnectionError as e:
        logger.warning(f"Claude connection error (will retry): {e}")
        raise
    except anthropic.APIError as e:
        logger.error(f"Claude API error (will not retry): {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise

def clean_json_response(text: str) -> str:
    text = text.strip()
    text = re.sub(r'```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    return text.strip()