"""
llm_clients.py — reusable, rate-limited LLM client for the conjecture
generator using AWS Bedrock (Gemma 3 27B).
"""

import logging
import os
import random
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

try:
    import boto3
    from botocore.exceptions import ClientError
    BEDROCK_AVAILABLE = True
except ImportError:
    BEDROCK_AVAILABLE = False


class RateLimiter:
    """Enforces a maximum request rate per minute across all pipeline calls."""

    def __init__(self, requests_per_minute: float = 60.0):
        self.interval = 60.0 / requests_per_minute
        self.last_call_time = 0.0

    def wait(self) -> None:
        now = time.time()
        elapsed = now - self.last_call_time
        if elapsed < self.interval:
            sleep_duration = self.interval - elapsed
            logger.info(f"RateLimiter: pausing {sleep_duration:.2f}s to respect rate limit...")
            time.sleep(sleep_duration)
        self.last_call_time = time.time()


# Shared limiter — set to 60 RPM for AWS Bedrock throughput
gemini_rate_limiter = RateLimiter(requests_per_minute=60.0)

# Initialize AWS Bedrock client
bedrock_client = (
    boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    if BEDROCK_AVAILABLE
    else None
)


def _strip_markdown_fences(text: str) -> str:
    """Strips markdown ```json and ``` wrappers from LLM responses."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def live_gemini_client(system_prompt: str, user_prompt: str, max_retries: int = 4) -> str:
    """
    Wrapper matching Callable[[str, str], str] with embedded rate limiting
    and backoff, configured for Google Gemma 3 27B via AWS Bedrock.
    """
    if not BEDROCK_AVAILABLE or bedrock_client is None:
        raise RuntimeError("boto3 is not installed or AWS Bedrock client failed to initialize.")

    model_id = os.environ.get("BEDROCK_MODEL_ID", "google.gemma-3-27b-it")

    for attempt in range(max_retries):
        gemini_rate_limiter.wait()
        logger.info(f"Sending request to Bedrock ({model_id}) (attempt {attempt + 1}/{max_retries})...")

        try:
            response = bedrock_client.converse(
                modelId=model_id,
                system=[{"text": system_prompt}],
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": user_prompt}],
                    }
                ],
                inferenceConfig={
                    "maxTokens": 1000,
                    "temperature": 0.2,
                },
            )
            logger.info("Received response from AWS Bedrock API.")
            raw_text = response["output"]["message"]["content"][0]["text"]
            return _strip_markdown_fences(raw_text)

        except Exception as e:
            error_msg = str(e)
            is_throttled = "ThrottlingException" in error_msg or "429" in error_msg or "TooManyRequests" in error_msg

            if is_throttled and attempt < max_retries - 1:
                backoff = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"Bedrock rate limited (attempt {attempt + 1}/{max_retries}); "
                    f"backing off {backoff:.1f}s before retry..."
                )
                time.sleep(backoff)
                continue
            raise

    raise RuntimeError("Exceeded max retries after repeated AWS Bedrock rate limits.")