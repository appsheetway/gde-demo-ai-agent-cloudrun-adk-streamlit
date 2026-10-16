# agent.py
import json

import httpx

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.genai import types

# [START get_menu]
def get_menu() -> str:
    """Retrieves the coffee shop menu from menu.json.
    
    Returns:
        str: A JSON string representing the list of menu items.
    """
    try:
        with open("menu.json", "r") as f:
            menu_data = json.load(f)
            return json.dumps(menu_data)
    except Exception as e:
        return json.dumps({"error": f"Could not retrieve menu: {str(e)}"})
# [END get_menu]

PRIMARY_MODEL = "gemini-3.5-flash"

# Each Gemini model has its own share of the project's throughput, so on a 429
# we fall back to lighter models instead of failing. Measured on this project:
# every model tops out around 100-125 calls/min on its own.
FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

# The primary model sometimes queues for 30-60s under shared load; give up
# after this long and let a (much faster, ~1-3s) fallback model answer instead.
# Timeouts are also retried by google-genai, so worst case is attempts x timeout.
PRIMARY_TIMEOUT_MS = 15_000
FALLBACK_TIMEOUT_MS = 10_000

# Quota errors, overloaded backends and server-side deadline (504 or 499,
# returned when PRIMARY_TIMEOUT_MS is hit): worth retrying or falling back.
RETRYABLE_CODES = (429, 499, 503, 504)


def _should_fall_back(error: Exception) -> bool:
    return getattr(error, "code", None) in RETRYABLE_CODES or isinstance(error, httpx.TimeoutException)


def _retry_options(attempts: int, max_delay: float) -> types.HttpRetryOptions:
    return types.HttpRetryOptions(
        attempts=attempts,
        initial_delay=1,
        max_delay=max_delay,
        exp_base=2,
        http_status_codes=[429, 499, 500, 503, 504],
    )


# [START model_fallback]
async def fallback_on_quota_error(callback_context, llm_request, error):
    """Retries the failed request on FALLBACK_MODELS when the primary model is out of quota or too slow.

    Returns the first successful response, or None to let ADK raise the
    original error.
    """
    if not _should_fall_back(error):
        return None

    last_error = error
    for i, model_name in enumerate(FALLBACK_MODELS):
        is_last = i == len(FALLBACK_MODELS) - 1
        request = llm_request.model_copy(deep=True)
        request.model = model_name
        # Fail over quickly on intermediate models; on the last one wait
        # longer (~1 min total) to ride out a burst instead of erroring.
        http_options = request.config.http_options
        http_options.retry_options = (
            _retry_options(attempts=7, max_delay=20) if is_last else _retry_options(attempts=2, max_delay=2)
        )
        http_options.timeout = None if is_last else FALLBACK_TIMEOUT_MS
        try:
            # A fresh Gemini per call: its async client must not outlive the
            # event loop that app.py creates for each message.
            async for response in Gemini(model=model_name).generate_content_async(request):
                return response
        except Exception as e:  # noqa: BLE001
            if not _should_fall_back(e):
                raise
            last_error = e
    raise last_error
# [END model_fallback]


# Create the barista agent
barista_agent = LlmAgent(
    name="barista_agent",
    model=PRIMARY_MODEL,
    instruction="""You are a friendly barista at ☕ Coffee Shop.
Your job is to recommend drinks and pastries to customers based on their preferences.

Rules you MUST follow:
1. You must recommend items ONLY from the menu returned by get_menu().
2. Do NOT recommend or suggest any item that is not present in the menu.
3. If a user's preference is vague or unclear, ask exactly ONE friendly clarifying question to narrow down what they want (e.g., cold or hot, sweet or strong, coffee or pastry).
4. Be warm and welcoming, but remain professional.
5. Ground your recommendations in the actual tags, descriptions, and allergens listed in the menu (e.g., if a user is dairy-free, recommend ONLY items tagged 'dairy-free' or with no dairy allergens).
""",
    tools=[get_menu],
    # Short per-request retry on the primary model (model is kept as a string,
    # not a shared Gemini object, because app.py creates a new event loop per
    # message and a cached async client would be bound to a closed loop).
    generate_content_config=types.GenerateContentConfig(
        http_options=types.HttpOptions(
            timeout=PRIMARY_TIMEOUT_MS,
            retry_options=_retry_options(attempts=2, max_delay=2),
        )
    ),
    on_model_error_callback=fallback_on_quota_error,
)

from google.adk.apps import App

# Define the App object
app = App(
    name="coffee_barista_app",
    root_agent=barista_agent
)