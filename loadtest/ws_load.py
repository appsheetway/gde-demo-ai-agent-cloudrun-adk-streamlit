# loadtest/ws_load.py
"""End-to-end load test of the Streamlit app over its WebSocket protocol.

Each virtual user behaves like a browser tab: it opens the WebSocket, loads
the page, sends chat messages through st.chat_input, then keeps the connection
open (idle) like a real attendee. This exercises Cloud Run concurrency,
autoscaling and Gemini together.

Usage:
    python loadtest/ws_load.py --url https://coffee-barista-380921864905.us-central1.run.app --users 50
    python loadtest/ws_load.py --url http://localhost:8501 --users 10 --hold 30

Requires the server to run with --server.enableXsrfProtection=false
(as configured on Cloud Run).
"""
import argparse
import asyncio
import random
import statistics
import time
from collections import Counter
from urllib.parse import urlparse

import websockets
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ClientState_pb2 import ClientState
from streamlit.proto.Common_pb2 import ChatInputValue
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.proto.WidgetStates_pb2 import WidgetState

PROMPTS = [
    "I want a strong, cold, dairy-free drink. Recommend one item and explain why.",
    "I have a dairy allergy. Which menu items should I avoid? Please explain the allergens.",
    "I want something sweet.",
    "Do you have a Matcha Strawberry Frappuccino? If not, recommend the closest item from the actual menu.",
    "Which menu items are explicitly dairy-free and sugar-free?",
]
BUSY_TEXT = "very busy"


class RunResult:
    def __init__(self):
        self.chat_input_id = None
        self.markdown = []
        self.alerts = []


async def run_script(ws, widget_states, timeout):
    """Send a rerun and collect deltas until the script finishes."""
    msg = BackMsg()
    msg.rerun_script.CopyFrom(ClientState(query_string="", page_script_hash=""))
    for w in widget_states:
        msg.rerun_script.widget_states.widgets.append(w)
    await ws.send(msg.SerializeToString())

    result = RunResult()
    deadline = time.monotonic() + timeout
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
        fwd = ForwardMsg()
        fwd.ParseFromString(raw)
        kind = fwd.WhichOneof("type")
        if kind == "delta" and fwd.delta.WhichOneof("type") == "new_element":
            el = fwd.delta.new_element
            el_type = el.WhichOneof("type")
            if el_type == "chat_input":
                result.chat_input_id = el.chat_input.id
            elif el_type == "markdown":
                result.markdown.append(el.markdown.body)
            elif el_type == "alert":
                result.alerts.append(el.alert.body)
        elif kind == "script_finished":
            return result


async def run_user(idx, args, stats):
    parsed = urlparse(args.url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = f"{scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/_stcore/stream"
    origin = f"{parsed.scheme}://{parsed.netloc}"

    t0 = time.perf_counter()
    try:
        async with websockets.connect(
            ws_url,
            subprotocols=["streamlit"],
            origin=origin,
            open_timeout=args.timeout,
            max_size=None,
            ping_interval=20,
        ) as ws:
            stats["connected"] += 1
            page = await run_script(ws, [], args.timeout)
            stats["page_load"].append(time.perf_counter() - t0)
            if not page.chat_input_id:
                stats["errors"]["chat_input not found"] += 1
                return

            for turn in range(args.turns):
                await asyncio.sleep(random.uniform(*args.think))
                prompt = random.choice(PROMPTS)
                if random.random() < args.free_ratio:
                    # Unique wording -> cache miss, like an attendee typing their own question.
                    prompt = f"{prompt} (I'm guest #{idx}, turn {turn})"
                state = WidgetState(id=page.chat_input_id, chat_input_value=ChatInputValue(data=prompt))
                t1 = time.perf_counter()
                res = await run_script(ws, [state], args.timeout)
                latency = time.perf_counter() - t1
                if any(BUSY_TEXT in a for a in res.alerts):
                    stats["errors"]["busy (429 after retries)"] += 1
                elif res.alerts:
                    stats["errors"]["app error: " + res.alerts[-1][:60]] += 1
                else:
                    stats["turn_latency"].append(latency)
                    stats["turns_ok"] += 1

            # Stay connected like an idle attendee: this is what holds Cloud Run concurrency.
            await asyncio.sleep(args.hold)
            stats["completed"] += 1
    except websockets.InvalidStatus as e:
        stats["errors"][f"connect HTTP {e.response.status_code}"] += 1
    except (asyncio.TimeoutError, TimeoutError):
        stats["errors"]["timeout"] += 1
    except websockets.ConnectionClosed as e:
        stats["errors"][f"connection closed ({e.code})"] += 1
    except Exception as e:  # noqa: BLE001
        stats["errors"][type(e).__name__] += 1


def pct(values, p):
    if not values:
        return float("nan")
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


def fmt(values):
    if not values:
        return "n/a"
    return (f"p50 {pct(values, 50):.1f}s | p90 {pct(values, 90):.1f}s | p99 {pct(values, 99):.1f}s | "
            f"max {max(values):.1f}s | mean {statistics.mean(values):.1f}s")


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="app URL, e.g. https://...run.app or http://localhost:8501")
    parser.add_argument("--users", type=int, default=20, help="concurrent browser sessions (default 20)")
    parser.add_argument("--turns", type=int, default=2, help="chat messages per user (default 2)")
    parser.add_argument("--ramp", type=float, default=30, help="seconds to open all sessions (default 30)")
    parser.add_argument("--think", type=float, nargs=2, default=(3, 10), metavar=("MIN", "MAX"),
                        help="seconds before each message (default 3 10)")
    parser.add_argument("--hold", type=float, default=60, help="idle seconds to stay connected after chatting (default 60)")
    parser.add_argument("--free-ratio", type=float, default=0.3,
                        help="share of messages with unique wording that bypass the response cache (default 0.3)")
    parser.add_argument("--timeout", type=float, default=120, help="per-step timeout in seconds (default 120)")
    args = parser.parse_args()

    stats = {"connected": 0, "completed": 0, "turns_ok": 0, "page_load": [], "turn_latency": [],
             "errors": Counter()}
    print(f"Target {args.url}: {args.users} users over {args.ramp}s, {args.turns} turns each, hold {args.hold}s, "
          f"free-ratio {args.free_ratio}")

    async def progress():
        while True:
            await asyncio.sleep(10)
            print(f"  [{time.strftime('%H:%M:%S')}] connected={stats['connected']} turns_ok={stats['turns_ok']} "
                  f"errors={sum(stats['errors'].values())}")

    reporter = asyncio.create_task(progress())
    start = time.perf_counter()
    tasks = []
    for i in range(args.users):
        tasks.append(asyncio.create_task(run_user(i, args, stats)))
        if args.ramp:
            await asyncio.sleep(args.ramp / args.users)
    await asyncio.gather(*tasks)
    reporter.cancel()

    print("\n========== WebSocket load test report ==========")
    print(f"Users            : {args.users}")
    print(f"Connected        : {stats['connected']}")
    print(f"Completed        : {stats['completed']}")
    print(f"Chat turns ok    : {stats['turns_ok']} / {args.users * args.turns}")
    print(f"Page load        : {fmt(stats['page_load'])}")
    print(f"Chat latency     : {fmt(stats['turn_latency'])}")
    print(f"Wall time        : {time.perf_counter() - start:.1f}s")
    if stats["errors"]:
        print("Errors           :")
        for name, count in stats["errors"].most_common():
            print(f"  - {name}: {count}")
    print("================================================")


if __name__ == "__main__":
    asyncio.run(main())
