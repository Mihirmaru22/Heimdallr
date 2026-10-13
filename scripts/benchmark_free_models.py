"""Automated Free Model Reliability Benchmark for Argus.

Tests all free models on OpenRouter with 2 consecutive burst calls per round.
Measures latency, HTTP status (429/500/etc.), and strict Pydantic JSON schema adherence.
Repeats every 3600s for a configured number of rounds (default 5).
Updates docs/FREE_MODEL_LEADERBOARD.md and data/free_model_benchmarks.json after every round.
Runs entirely in the background without interfering with developer activities.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import sys
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from argus.llm.openrouter import extract_json_payload


# --- Test Schemas and Prompts ---

class FacilityExtraction(BaseModel):
    company_name: str = Field(description="Name of the automotive manufacturer")
    facility_name: str = Field(description="Name of the manufacturing plant")
    plant_manager: str = Field(description="Name of the plant manager or director")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    key_details: list[str] = Field(description="Key bullet points extracted from the text")


PROMPT_CALL_1 = (
    "Extract the facility information from this text snippet:\n"
    "\"Ford Motor Company operates the Kentucky Truck Plant located in Louisville, Kentucky. "
    "As of 2024, John Bell serves as the Plant Manager overseeing production of the Ford Super Duty, "
    "Expedition, and Lincoln Navigator. The facility employs over 9,000 workers across three shifts.\""
)

PROMPT_CALL_2 = (
    "Extract the facility information from this text snippet:\n"
    "\"General Motors operates the Fort Wayne Assembly plant in Roanoke, Indiana. "
    "Garry Campbell serves as the Plant Executive Director. The facility produces Chevrolet Silverado "
    "and GMC Sierra light-duty pickup trucks and has received multiple quality awards.\""
)


# --- Utility Functions ---

def load_api_key() -> str:
    """Find OpenRouter API key from env or .env files."""
    for key_name in ("OPENROUTER_API_KEY", "OPEN_ROUTER_API"):
        if os.getenv(key_name):
            return os.getenv(key_name, "")
    for env_path in ("docs/.env", ".env"):
        if os.path.isfile(env_path):
            try:
                with open(env_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith(("OPEN_ROUTER_API", "OPENROUTER_API_KEY")):
                            parts = line.strip().split("=", 1)
                            if len(parts) == 2:
                                return parts[1].strip()
            except OSError:
                pass
    return ""


async def fetch_free_text_models(api_key: str, client: httpx.AsyncClient) -> list[str]:
    """Fetch all free chat/text models from OpenRouter."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        resp = await client.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=15.0)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            free_models: list[str] = []
            for m in data:
                m_id = m.get("id", "")
                pricing = m.get("pricing", {})
                is_free = m_id.endswith(":free") or (
                    pricing.get("prompt") == "0" and pricing.get("completion") == "0"
                )
                if not is_free:
                    continue

                # Filter out audio-only or moderation models
                modality = m.get("architecture", {}).get("modality", "")
                if "audio" in modality and "text" not in modality:
                    continue
                if "content-safety" in m_id:
                    continue
                if "lyria" in m_id:
                    continue

                free_models.append(m_id)
            free_models.sort()
            return free_models
    except Exception as e:
        logging.warning("Failed to dynamically fetch models: %s", e)

    # Fallback list if network query fails
    return [
        "openrouter/free",
        "qwen/qwen3.8-27b:free",
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3.5-lightning:free",
        "liquid/lfm-2.5-2.6b:free",
        "poolside/laguna-s-2.1:free",
        "poolside/laguna-xs-2.1:free",
        "thinkingmachines/inkling:free",
        "thinkingmachines/inkling-small:free",
        "cohere/north-mini-code:free",
        "apodex/apodex-1.1-mini:free",
        "dots-studio/dots-3-note-preview:free",
        "inclusionai/ling-3.1-flash",
        "inclusionai/ling-3.0-flash-sante:free",
        "stealth/space-bunny-alpha",
    ]


async def run_single_probe(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    prompt: str,
    call_index: int,
    timeout: float = 35.0,
) -> dict[str, Any]:
    """Execute a single structured extraction call against a model."""
    schema = FacilityExtraction.model_json_schema()
    schema_instruction = (
        f"You MUST respond ONLY with a valid JSON object strictly conforming to the following JSON schema:\n"
        f"{json.dumps(schema, indent=2)}\n"
        f"Do not include any Markdown wrapping (e.g. ```json), commentary, or text outside the JSON object."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": schema_instruction},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/argus-research/argus",
        "X-Title": "Argus Free Model Benchmark",
        "Content-Type": "application/json",
    }

    start_time = time.perf_counter()
    status = "UNKNOWN"
    status_code = 0
    latency = 0.0
    error_msg = ""
    parsed_successfully = False

    try:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        latency = round(time.perf_counter() - start_time, 2)
        status_code = response.status_code

        if status_code == 200:
            res_json = response.json()
            choices = res_json.get("choices", [])
            if not choices:
                status = "EMPTY_CHOICES"
                error_msg = "API returned 200 but no choices"
            else:
                raw_text = choices[0].get("message", {}).get("content", "")
                cleaned = extract_json_payload(raw_text)
                try:
                    data = json.loads(cleaned)
                    FacilityExtraction.model_validate(data)
                    parsed_successfully = True
                    status = "SUCCESS"
                except Exception as val_err:
                    status = "SCHEMA_ERROR"
                    error_msg = f"Schema parse error: {str(val_err)[:80]}"
        elif status_code == 429:
            status = "429_RATE_LIMITED"
            error_msg = "HTTP 429 Too Many Requests"
        elif status_code in (500, 502, 503, 504):
            status = f"HTTP_{status_code}_SERVER_ERROR"
            error_msg = f"Server error: {response.text[:80]}"
        else:
            status = f"HTTP_{status_code}"
            error_msg = f"Unexpected response: {response.text[:80]}"

    except httpx.TimeoutException:
        latency = round(time.perf_counter() - start_time, 2)
        status = "TIMEOUT"
        error_msg = f"Request timed out (> {timeout}s)"
    except Exception as exc:
        latency = round(time.perf_counter() - start_time, 2)
        status = "CLIENT_ERROR"
        error_msg = str(exc)[:80]

    return {
        "call_index": call_index,
        "status": status,
        "status_code": status_code,
        "latency_sec": latency,
        "parsed_schema": parsed_successfully,
        "error": error_msg,
    }


def generate_markdown_report(history: dict[str, Any], output_path: str) -> None:
    """Generate the markdown leaderboard from test history."""
    rounds = history.get("rounds", [])
    total_rounds_configured = history.get("total_rounds_configured", 5)
    last_updated = history.get("last_updated", "N/A")
    next_round_at = history.get("next_round_at", "Completed")

    # Aggregate stats per model
    model_stats: dict[str, dict[str, Any]] = {}

    for r in rounds:
        r_num = r.get("round_number", 0)
        for m_id, res in r.get("models", {}).items():
            if m_id not in model_stats:
                model_stats[m_id] = {
                    "total_calls": 0,
                    "successful_calls": 0,
                    "burst_success_rounds": 0,
                    "total_rounds": 0,
                    "latencies": [],
                    "errors": set(),
                }
            stats = model_stats[m_id]
            stats["total_rounds"] += 1
            call1 = res.get("call_1", {})
            call2 = res.get("call_2", {})

            stats["total_calls"] += 2
            if call1.get("status") == "SUCCESS":
                stats["successful_calls"] += 1
                stats["latencies"].append(call1.get("latency_sec", 0))
            else:
                stats["errors"].add(f"R{r_num}: {call1.get('status')}")

            if call2.get("status") == "SUCCESS":
                stats["successful_calls"] += 1
                stats["latencies"].append(call2.get("latency_sec", 0))
            else:
                stats["errors"].add(f"R{r_num}: {call2.get('status')} (Burst)")

            if call1.get("status") == "SUCCESS" and call2.get("status") == "SUCCESS":
                stats["burst_success_rounds"] += 1

    # Sort models by success rate desc, then avg latency asc
    sorted_models = []
    for m_id, st in model_stats.items():
        total_calls = st["total_calls"]
        success_rate = (st["successful_calls"] / total_calls * 100) if total_calls > 0 else 0
        burst_rate = (st["burst_success_rounds"] / st["total_rounds"] * 100) if st["total_rounds"] > 0 else 0
        avg_latency = round(sum(st["latencies"]) / len(st["latencies"]), 2) if st["latencies"] else 999.0
        sorted_models.append((m_id, success_rate, burst_rate, avg_latency, st))

    sorted_models.sort(key=lambda x: (-x[1], -x[2], x[3]))

    lines = [
        "# Argus Free Model Reliability Leaderboard",
        "",
        f"> **Last Updated:** `{last_updated}`  ",
        f"> **Progress:** Round {len(rounds)} of {total_rounds_configured} completed  ",
        f"> **Next Round:** `{next_round_at}`  ",
        "",
        "## 1. Reliability Matrix",
        "",
        "| Model ID | Success Rate | Burst Pass Rate | Avg Latency | Status / Verdict | Primary Role in Argus |",
        "| :--- | :---: | :---: | :---: | :--- | :--- |",
    ]

    for m_id, success_rate, burst_rate, avg_latency, st in sorted_models:
        if success_rate >= 90.0 and burst_rate >= 90.0 and avg_latency < 10.0:
            verdict = "🟢 **Rock Solid**"
            role = "Worker / Verifier (Fast)"
        elif success_rate >= 80.0:
            verdict = "🟡 **Viable** (Occasional Throttle)"
            role = "Backup Worker / Brain"
        elif success_rate >= 50.0:
            verdict = "🟠 **Unstable** (Frequent 429)"
            role = "Non-critical Fallback"
        else:
            verdict = "🔴 **Betrayal Risk** (Fails/Corrupt)"
            role = "❌ Do Not Use"

        lat_str = f"{avg_latency}s" if avg_latency < 900 else "N/A"
        err_note = f"<br><sub>Errors: {', '.join(list(st['errors'])[:2])}</sub>" if st["errors"] else ""
        lines.append(
            f"| `{m_id}` | **{success_rate:.0f}%** ({st['successful_calls']}/{st['total_calls']}) | {burst_rate:.0f}% | {lat_str} | {verdict}{err_note} | {role} |"
        )

    lines.extend([
        "",
        "## 2. Test Specification",
        "",
        "* **Consecutive Burst Calls:** 2 sequential calls per model per hourly round.",
        "* **Schema Enforcement:** Strict Pydantic JSON structure extraction (`FacilityExtraction`).",
        "* **Betrayal Criteria:** Any `HTTP 429` rate limit, `TIMEOUT > 35s`, server drop `502/503`, or JSON schema mismatch.",
        "",
        "## 3. Hourly Round History",
        "",
    ])

    for r in reversed(rounds):
        r_num = r.get("round_number")
        timestamp = r.get("timestamp")
        m_results = r.get("models", {})
        succeeded = sum(1 for m in m_results.values() if m.get("call_1", {}).get("status") == "SUCCESS" and m.get("call_2", {}).get("status") == "SUCCESS")
        lines.append(f"### Round {r_num} — `{timestamp}`")
        lines.append(f"* **Models Tested:** {len(m_results)}")
        lines.append(f"* **Fully Succeeded (Burst Passed):** {succeeded}/{len(m_results)}")
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# --- Main Loop ---

async def main_async(args: argparse.Namespace) -> None:
    api_key = load_api_key()
    if not api_key:
        logging.error("No OpenRouter API key found in docs/.env or environment!")
        sys.exit(1)

    os.makedirs(os.path.dirname(args.output_md), exist_ok=True)
    os.makedirs(os.path.dirname(args.log_json), exist_ok=True)

    # Load existing history if present
    history: dict[str, Any] = {
        "total_rounds_configured": args.rounds,
        "rounds": [],
    }
    if os.path.isfile(args.log_json):
        try:
            with open(args.log_json, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    history["total_rounds_configured"] = args.rounds

    current_round = len(history.get("rounds", [])) + 1
    logging.info("Starting Free Model Benchmark. Total rounds: %d, Interval: %ds", args.rounds, args.interval)

    async with httpx.AsyncClient(timeout=45.0) as client:
        while current_round <= args.rounds:
            round_start = datetime.now(timezone.utc).isoformat()
            logging.info("=== Starting Round %d of %d at %s ===", current_round, args.rounds, round_start)

            # Discover models
            models = await fetch_free_text_models(api_key, client)
            logging.info("Evaluating %d free text models...", len(models))

            round_data: dict[str, Any] = {
                "round_number": current_round,
                "timestamp": round_start,
                "models": {},
            }

            for model in models:
                logging.info("[%s] Testing Call 1 (Normal)...", model)
                call1 = await run_single_probe(client, api_key, model, PROMPT_CALL_1, 1, timeout=args.timeout)
                logging.info(
                    "[%s] Call 1 result: %s (latency: %ss)",
                    model, call1["status"], call1["latency_sec"]
                )

                # Small breather (0.3s) then immediate burst Call 2
                await asyncio.sleep(0.3)
                logging.info("[%s] Testing Call 2 (Immediate Burst)...", model)
                call2 = await run_single_probe(client, api_key, model, PROMPT_CALL_2, 2, timeout=args.timeout)
                logging.info(
                    "[%s] Call 2 result: %s (latency: %ss)",
                    model, call2["status"], call2["latency_sec"]
                )

                round_data["models"][model] = {
                    "call_1": call1,
                    "call_2": call2,
                }

                # Polite pause between different models to avoid local socket exhaustion
                await asyncio.sleep(1.0)

            history["rounds"].append(round_data)
            history["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            if current_round < args.rounds:
                next_epoch = time.time() + args.interval
                history["next_round_at"] = datetime.fromtimestamp(next_epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            else:
                history["next_round_at"] = "All 5 rounds completed"

            # Save state
            with open(args.log_json, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)

            generate_markdown_report(history, args.output_md)
            logging.info("Round %d complete! Leaderboard updated at %s", current_round, args.output_md)

            if current_round >= args.rounds:
                logging.info("All %d rounds finished successfully.", args.rounds)
                break

            logging.info("Sleeping for %d seconds until next round...", args.interval)
            current_round += 1
            await asyncio.sleep(args.interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Argus Free Model Reliability Benchmark")
    parser.add_argument("--rounds", type=int, default=5, help="Number of hourly rounds to execute")
    parser.add_argument("--interval", type=int, default=3600, help="Interval between rounds in seconds (default: 3600)")
    parser.add_argument("--timeout", type=float, default=35.0, help="Per-call timeout in seconds (default: 35.0)")
    parser.add_argument("--output-md", default="docs/FREE_MODEL_LEADERBOARD.md", help="Path to markdown output")
    parser.add_argument("--log-json", default="data/free_model_benchmarks.json", help="Path to JSON history")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
