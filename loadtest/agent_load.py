# loadtest/agent_load.py
"""Load test the agent + Gemini layer directly (no Streamlit, no Cloud Run).

Simulates N concurrent conversations against barista_agent to find the point
where Gemini starts returning 429 / latency degrades.

Usage (from repo root):
    python loadtest/agent_load.py --users 50
    python loadtest/agent_load.py --users 200 --ramp 20 --no-retry
"""
import argparse
import asyncio
import os
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
# get_menu() opens "menu.json" relative to the working directory.
os.chdir(REPO_ROOT)

# Same settings as the Cloud Run service.
os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "youtube-drive-auto-upload")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from agent import app, barista_agent  # noqa: E402

# Prompts from knowledge-base/Demo-Runbook-vi.md
CONVERSATIONS = [
    ["I want a strong, cold, dairy-free drink. Recommend one item and explain why."],
    ["I have a dairy allergy. Which menu items should I avoid? Please explain the allergens.",
     "Which menu items are explicitly dairy-free?"],
    ["I want something sweet.", "Cold, please."],
    ["Do you have a Matcha Strawberry Frappuccino? If not, recommend the closest item from the actual menu."],
    ["Which menu items are explicitly dairy-free and sugar-free?"],
]


def classify_error(e: Exception) -> str:
    msg = str(e)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "429 RESOURCE_EXHAUSTED"
    if "503" in msg or "UNAVAILABLE" in msg:
        return "503 UNAVAILABLE"
    if "500" in msg or "INTERNAL" in msg:
        return "500 INTERNAL"
    return type(e).__name__


async def run_user(runner, user_idx, args, results):
    user_id = f"load-user-{user_idx}"
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id=user_id
    )
    turns = random.choice(CONVERSATIONS)[: args.turns]
    for i, prompt in enumerate(turns):
        if i:
            await asyncio.sleep(random.uniform(*args.think))
        start = time.perf_counter()
        record = {"ok": False, "tool_called": False, "error": None}
        try:
            text = ""
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
            ):
                if event.get_function_calls():
                    record["tool_called"] = True
                if event.content and event.content.parts:
                    text += "".join(p.text for p in event.content.parts if p.text)
            record["ok"] = bool(text.strip())
            if not record["ok"]:
                record["error"] = "empty response"
        except Exception as e:  # noqa: BLE001
            record["error"] = classify_error(e)
        record["latency"] = time.perf_counter() - start
        results.append(record)


def pct(values, p):
    if not values:
        return float("nan")
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


def print_report(results, wall):
    ok = [r for r in results if r["ok"]]
    lat = [r["latency"] for r in ok]
    errors = Counter(r["error"] for r in results if r["error"])
    print("\n========== Agent load test report ==========")
    print(f"Turns total      : {len(results)}")
    print(f"Succeeded        : {len(ok)} ({len(ok) / max(1, len(results)):.1%})")
    print(f"Tool get_menu()  : called in {sum(r['tool_called'] for r in results)} turns")
    print(f"Wall time        : {wall:.1f}s  ->  {len(results) / wall * 60:.0f} turns/min")
    if lat:
        print(f"Latency (ok)     : p50 {pct(lat, 50):.1f}s | p90 {pct(lat, 90):.1f}s | "
              f"p99 {pct(lat, 99):.1f}s | max {max(lat):.1f}s | mean {statistics.mean(lat):.1f}s")
    if errors:
        print("Errors           :")
        for name, count in errors.most_common():
            print(f"  - {name}: {count}")
    print("============================================")


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--users", type=int, default=20, help="concurrent conversations (default 20)")
    parser.add_argument("--turns", type=int, default=2, help="max prompts per conversation (default 2)")
    parser.add_argument("--ramp", type=float, default=5, help="seconds to start all users (default 5; 0 = burst)")
    parser.add_argument("--think", type=float, nargs=2, default=(2, 5), metavar=("MIN", "MAX"),
                        help="think time between turns in seconds (default 2 5)")
    parser.add_argument("--model", help="override the agent model (e.g. gemini-2.5-flash) to compare capacity")
    parser.add_argument("--no-fallback", action="store_true",
                        help="disable falling back to lighter models on 429")
    parser.add_argument("--no-retry", action="store_true",
                        help="disable Gemini retries to see raw 429s")
    args = parser.parse_args()

    if args.model:
        barista_agent.model = args.model
    if args.no_fallback:
        barista_agent.on_model_error_callback = None
    if args.no_retry:
        barista_agent.generate_content_config.http_options.retry_options = None

    print(f"Project={os.environ['GOOGLE_CLOUD_PROJECT']} location={os.environ['GOOGLE_CLOUD_LOCATION']} "
          f"model={barista_agent.model} retry={'off' if args.no_retry else 'on'} "
          f"fallback={'off' if args.no_fallback else 'on'}")
    print(f"Starting {args.users} users over {args.ramp}s, up to {args.turns} turns each...")

    runner = InMemoryRunner(app=app)
    results = []
    start = time.perf_counter()
    tasks = []
    for i in range(args.users):
        tasks.append(asyncio.create_task(run_user(runner, i, args, results)))
        if args.ramp:
            await asyncio.sleep(args.ramp / args.users)
    await asyncio.gather(*tasks)
    print_report(results, time.perf_counter() - start)


if __name__ == "__main__":
    asyncio.run(main())
