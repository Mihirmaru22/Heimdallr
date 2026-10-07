# Heimdallr Vertical Capability Audit: Blackbird Capability & Architecture Note

This document establishes the baseline architecture, execution path, and failure modes of Blackbird as an open-source identity-correlation / identity-expansion candidate specialist for Heimdallr.

---

## 1. Blackbird Architecture & Capability Trace

```
BLACKBIRD CAPABILITY: Automated Cross-Platform Username and Email Account Discovery
→ INPUT:
  - Target username string (e.g., "johndoe", "sarah_engineer") OR email address.
  - Optional search filter parameters (e.g., platform category, NSFW filter).

→ PROCESSING:
  - Loads a target list of 600+ web platforms derived from the open-source WhatsMyName database schema (`data.json`).
  - Constructs platform-specific probe URLs by substituting the target identifier (e.g., `https://github.com/{username}`).
  - Asynchronously dispatches concurrent HTTP GET/POST probes using `aiohttp` throttled by `asyncio.Semaphore`.
  - Evaluates HTTP response status code and response body content against platform-specific response signatures:
    - Match condition: `response.status_code == site["e_code"]` AND `site["e_string"] in response.text`
    - Absence condition: `site["m_string"] not in response.text` AND `response.status_code != site["m_code"]`
  - Extracts public profile metadata (bio, display name, location, avatar) when predefined regex scrapers match.

→ OUTPUT:
  - Structured list of confirmed accounts:
    `[{"platform": "GitHub", "url": "https://github.com/...", "status": "FOUND", "metadata": {...}}, ...]`
  - Export formats: JSON, CSV, PDF.

→ EVIDENCE / PROVENANCE:
  - Direct HTTP response verification: Status code, probed URL, timestamp, and signature string containment.
  - Lacks character-offset document unit spans or cryptographic content hashing.

→ FAILURE MODES:
  1. False Identity Merges (Username Collision): Unrelated individuals sharing common handles (e.g., "alex_m" on Spotify is completely unrelated to "alex_m" on GitHub). Blackbird treats all identical handles as a single individual.
  2. Anti-Bot / False Positives: Cloudflare, Akamai, or Captcha challenge pages frequently return 200 OK or unexpected HTML, tricking signature checks into reporting accounts as "FOUND".
  3. Stale Platform Signatures: Target sites frequently alter profile layout HTML, breaking `e_string` and `m_string` matching.
  4. Epistemic Blindness: Blackbird cannot infer whether an account is active, abandoned, or satirical; it only checks string presence.

→ ARGUS OVERLAP:
  - Near zero. Argus's `ContactResolutionEngine` handles corporate domain inference, DNS MX record validation, and executive appointment extraction from corporate disclosures. It does not probe consumer web platforms.

→ ARGUS GAP:
  - Argus has no capability to expand an individual investigator's target handle across the public developer, social, and forum ecosystem.
```

---

## 2. Licensing Audit

- **Repository**: `https://github.com/p1ngul1n0/blackbird` (owner: `antoniaci/blackbird`)
- **Author**: Lucas Antoniaci (`p1ngul1n0` / `antoniaci`)
- **Stars**: ~8,985 | **Forks**: ~1,054
- **License**: **`license: null` (NO OPEN SOURCE LICENSE FOUND)**
  - Under GitHub Terms of Service and international intellectual property law, repositories without an explicit license default to **"All Rights Reserved"** by the creator.
  - No license grant exists permitting distribution, modification, or inclusion into proprietary software systems like Heimdallr without explicit written agreement from the author.
  - This presents a fatal legal/compliance barrier unless the capability is implemented cleanly as an open-standard protocol or based on an unencumbered permissive alternative (e.g., WhatsMyName's MIT-licensed dataset).
