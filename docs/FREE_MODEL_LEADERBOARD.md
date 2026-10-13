# Argus Free Model Reliability Leaderboard

> **Last Updated:** `2026-10-05 10:17:32 UTC`  
> **Progress:** Round 5 of 5 completed  
> **Next Round:** `All 5 rounds completed`  

## 1. Reliability Matrix

| Model ID | Success Rate | Burst Pass Rate | Avg Latency | Status / Verdict | Primary Role in Argus |
| :--- | :---: | :---: | :---: | :--- | :--- |
| `cohere/north-mini-code:free` | **100%** (10/10) | 100% | 4.3s | 🟢 **Rock Solid** | Worker / Verifier (Fast) |
| `nvidia/nemotron-3-super-120b-a12b:free` | **100%** (10/10) | 100% | 4.36s | 🟢 **Rock Solid** | Worker / Verifier (Fast) |
| `dots-studio/dots-3-note-preview:free` | **100%** (10/10) | 100% | 9.06s | 🟢 **Rock Solid** | Worker / Verifier (Fast) |
| `nvidia/nemotron-3.5-lightning:free` | **100%** (10/10) | 100% | 30.54s | 🟡 **Viable** (Occasional Throttle) | Backup Worker / Brain |
| `openrouter/free` | **90%** (9/10) | 80% | 9.27s | 🟡 **Viable** (Occasional Throttle)<br><sub>Errors: R4: SCHEMA_ERROR</sub> | Backup Worker / Brain |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | **90%** (9/10) | 80% | 18.68s | 🟡 **Viable** (Occasional Throttle)<br><sub>Errors: R4: EMPTY_CHOICES</sub> | Backup Worker / Brain |
| `stealth/space-bunny-alpha` | **80%** (8/10) | 80% | 2.14s | 🟡 **Viable** (Occasional Throttle)<br><sub>Errors: R4: TIMEOUT (Burst), R4: EMPTY_CHOICES</sub> | Backup Worker / Brain |
| `liquid/lfm-2.5-2.6b:free` | **80%** (8/10) | 80% | 5.03s | 🟡 **Viable** (Occasional Throttle)<br><sub>Errors: R2: 429_RATE_LIMITED (Burst), R2: 429_RATE_LIMITED</sub> | Backup Worker / Brain |
| `apodex/apodex-1.1-mini:free` | **80%** (8/10) | 80% | 8.83s | 🟡 **Viable** (Occasional Throttle)<br><sub>Errors: R2: 429_RATE_LIMITED (Burst), R2: 429_RATE_LIMITED</sub> | Backup Worker / Brain |
| `qwen/qwen3.8-27b:free` | **70%** (7/10) | 60% | 11.23s | 🟠 **Unstable** (Frequent 429)<br><sub>Errors: R2: 429_RATE_LIMITED (Burst), R2: 429_RATE_LIMITED</sub> | Non-critical Fallback |
| `poolside/laguna-s-2.1:free` | **70%** (7/10) | 40% | 4.81s | 🟠 **Unstable** (Frequent 429)<br><sub>Errors: R1: 429_RATE_LIMITED, R3: 429_RATE_LIMITED (Burst)</sub> | Non-critical Fallback |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | **50%** (5/10) | 40% | 7.05s | 🟠 **Unstable** (Frequent 429)<br><sub>Errors: R2: EMPTY_CHOICES, R3: EMPTY_CHOICES (Burst)</sub> | Non-critical Fallback |
| `google/gemma-4-26b-a4b-it:free` | **0%** (0/10) | 0% | N/A | 🔴 **Betrayal Risk** (Fails/Corrupt)<br><sub>Errors: R3: 429_RATE_LIMITED (Burst), R1: 429_RATE_LIMITED (Burst)</sub> | ❌ Do Not Use |
| `google/gemma-4-31b-it:free` | **0%** (0/10) | 0% | N/A | 🔴 **Betrayal Risk** (Fails/Corrupt)<br><sub>Errors: R3: 429_RATE_LIMITED (Burst), R1: 429_RATE_LIMITED (Burst)</sub> | ❌ Do Not Use |
| `inclusionai/ling-3.0-flash-sante:free` | **0%** (0/10) | 0% | N/A | 🔴 **Betrayal Risk** (Fails/Corrupt)<br><sub>Errors: R1: HTTP_400 (Burst), R3: HTTP_400 (Burst)</sub> | ❌ Do Not Use |
| `inclusionai/ling-3.1-flash` | **0%** (0/10) | 0% | N/A | 🔴 **Betrayal Risk** (Fails/Corrupt)<br><sub>Errors: R3: 429_RATE_LIMITED (Burst), R1: HTTP_400 (Burst)</sub> | ❌ Do Not Use |
| `poolside/laguna-xs-2.1:free` | **0%** (0/10) | 0% | N/A | 🔴 **Betrayal Risk** (Fails/Corrupt)<br><sub>Errors: R3: 429_RATE_LIMITED (Burst), R5: CLIENT_ERROR</sub> | ❌ Do Not Use |
| `thinkingmachines/inkling-small:free` | **0%** (0/10) | 0% | N/A | 🔴 **Betrayal Risk** (Fails/Corrupt)<br><sub>Errors: R3: HTTP_403 (Burst), R5: HTTP_403</sub> | ❌ Do Not Use |
| `thinkingmachines/inkling:free` | **0%** (0/10) | 0% | N/A | 🔴 **Betrayal Risk** (Fails/Corrupt)<br><sub>Errors: R3: HTTP_403 (Burst), R5: HTTP_403</sub> | ❌ Do Not Use |

## 2. Test Specification

* **Consecutive Burst Calls:** 2 sequential calls per model per hourly round.
* **Schema Enforcement:** Strict Pydantic JSON structure extraction (`FacilityExtraction`).
* **Betrayal Criteria:** Any `HTTP 429` rate limit, `TIMEOUT > 35s`, server drop `502/503`, or JSON schema mismatch.

## 3. Hourly Round History

### Round 5 — `2026-10-05T10:13:41.211232+00:00`
* **Models Tested:** 19
* **Fully Succeeded (Burst Passed):** 12/19

### Round 4 — `2026-10-05T09:07:49.074537+00:00`
* **Models Tested:** 19
* **Fully Succeeded (Burst Passed):** 6/19

### Round 3 — `2026-10-05T08:03:59.849355+00:00`
* **Models Tested:** 19
* **Fully Succeeded (Burst Passed):** 10/19

### Round 2 — `2026-10-05T07:00:53.517561+00:00`
* **Models Tested:** 19
* **Fully Succeeded (Burst Passed):** 8/19

### Round 1 — `2026-10-05T05:56:39.607398+00:00`
* **Models Tested:** 19
* **Fully Succeeded (Burst Passed):** 11/19

