import logging
import os
import time
import unittest
from harness import SAM1_BINARY
from conjecture_generator import generate_conjecture_for_branch
from conjecture_validator import validate_conjecture

# Configure console logging output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

try:
    from google import genai
    GEMINI_SDK_TYPE = "genai"
except ImportError:
    try:
        import google.generativeai as genai_legacy
        GEMINI_SDK_TYPE = "legacy"
    except ImportError:
        GEMINI_SDK_TYPE = None


class RateLimiter:
    """Enforces a maximum request rate per minute across all pipeline calls."""
    def __init__(self, requests_per_minute: float = 9.0):
        self.interval = 60.0 / requests_per_minute
        self.last_call_time = 0.0

    def wait(self) -> None:
        now = time.time()
        elapsed = now - self.last_call_time
        if elapsed < self.interval:
            sleep_duration = self.interval - elapsed
            logger.info(f"RateLimiter: Pausing for {sleep_duration:.2f}s to respect 9 RPM limit...")
            time.sleep(sleep_duration)
        self.last_call_time = time.time()


gemini_rate_limiter = RateLimiter(requests_per_minute=9.0)


def live_gemini_client(system_prompt: str, user_prompt: str) -> str:
    """Wrapper matching Callable[[str, str], str] with embedded rate limiting and logging."""
    gemini_rate_limiter.wait()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    logger.info("Sending request to Gemini API...")
    if GEMINI_SDK_TYPE == "genai":
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",  # Updated to active model endpoint
            contents=f"{system_prompt}\n\n{user_prompt}"
        )
        logger.info("Received response from Gemini API.")
        return response.text or ""

    elif GEMINI_SDK_TYPE == "legacy":
        genai_legacy.configure(api_key=api_key)
        model = genai_legacy.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(f"{system_prompt}\n\n{user_prompt}")
        logger.info("Received response from Gemini API.")
        return response.text or ""

    raise RuntimeError("No compatible Google Gemini SDK installed.")


class TestLiveLLMIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        logger.info("Checking prerequisites for live Gemini integration test...")

        if not SAM1_BINARY.exists():
            msg = "SAM1 binary not found. Compile SAM1/SAM2 first."
            logger.warning(f"SKIP REASON: {msg}")
            raise unittest.SkipTest(msg)

        if GEMINI_SDK_TYPE is None:
            msg = "Gemini SDK not installed. Run `pip install google-genai`."
            logger.warning(f"SKIP REASON: {msg}")
            raise unittest.SkipTest(msg)

        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            msg = "GEMINI_API_KEY or GOOGLE_API_KEY environment variable is not set."
            logger.warning(f"SKIP REASON: {msg}")
            raise unittest.SkipTest(msg)

        logger.info("All prerequisites met. Running live integration test.")

    def test_live_gemini_generate_and_validate(self):
        """Pass COBOL AST branch to live Gemini API (<= 9 RPM) and validate output with SAM binary."""
        branch = {
            "conditions": ["TRAN-CODE = 'UPDATE'", "TRAN-FIELD-NAME = 'NAME'"],
            "path": [
                "000-MAIN",
                "200-PROCESS-TRAN",
                "IF TRAN-FIELD-NAME = 'NAME'",
                "MOVE TRAN-UPDATE-DATA TO CUST-NAME"
            ]
        }

        logger.info("Generating conjecture via Gemini...")
        conj = generate_conjecture_for_branch(branch, llm_client=live_gemini_client)

        logger.info("Executing ground-truth validation against SAM1 binary...")
        result = validate_conjecture(conj)

        self.assertTrue(
            result.passed,
            f"Gemini conjecture failed validation: {result.reason}\n"
            f"Generated Transaction: {conj.input_transactions}"
        )
        logger.info("Live integration test passed successfully!")


if __name__ == "__main__":
    unittest.main()