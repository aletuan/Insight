"""
AI enrichment service.

Provides summarization (Claude Haiku) and embedding (OpenAI) for ingested items.
"""
import json
import logging

import anthropic
import openai

from app.config import settings

logger = logging.getLogger(__name__)

SUMMARIZE_SYSTEM_PROMPT = """You are a concise research assistant. Given an article title and optionally its full text, produce a JSON object with exactly two keys:

- "summary": A 3-4 sentence summary of the content. Focus on the key ideas and why they matter. If only a title is provided (no content), write a brief 1-2 sentence description based on the title alone.
- "tags": An array of 2-5 lowercase topic tags (e.g. "machine-learning", "web-development", "startup-strategy"). Use hyphens for multi-word tags.

Respond with ONLY valid JSON, no markdown fences or extra text."""


def get_anthropic_client():
    """Return an async Anthropic client. Separated for easy mocking."""
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def get_openai_client():
    """Return an async OpenAI client. Separated for easy mocking."""
    return openai.AsyncOpenAI(api_key=settings.openai_api_key)


async def summarize_content(title: str, content: str | None) -> tuple[str, list[str]] | None:
    """Generate a summary and topic tags using Claude Haiku.

    Args:
        title: The item title.
        content: The extracted article text, or None if extraction failed.

    Returns:
        Tuple of (summary, tags) on success, or None on failure.
    """
    if content:
        user_message = f"Title: {title}\n\nContent:\n{content[:8000]}"
    else:
        user_message = f"Title: {title}\n\n(No article content available — summarize based on title only)"

    try:
        client = get_anthropic_client()
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=SUMMARIZE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw_text = message.content[0].text.strip()
        logger.debug(f"Haiku raw response: {raw_text[:200]}")
        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
            raw_text = raw_text.rsplit("```", 1)[0].strip()
        parsed = json.loads(raw_text)

        summary = parsed.get("summary", "")
        tags = parsed.get("tags", [])

        if not summary:
            logger.warning("Haiku returned empty summary")
            return None

        return summary, tags

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse Haiku JSON response: {e}")
        return None
    except Exception as e:
        logger.warning(f"Haiku summarization failed: {e}")
        return None


async def generate_embedding(text: str) -> list[float] | None:
    """Generate a 1536-dim embedding using OpenAI text-embedding-3-small.

    Args:
        text: The text to embed (typically title + summary).

    Returns:
        List of 1536 floats, or None on failure.
    """
    try:
        client = get_openai_client()
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],
        )
        embedding = response.data[0].embedding
        return embedding

    except Exception as e:
        logger.warning(f"OpenAI embedding failed: {e}")
        return None
