# HEIMDALLR VERTICAL 6: EMAIL & ACCOUNT INTELLIGENCE
## Candidate Landscape & Open-Source Capability Audit

### 1. Executive Summary & Audit Mandate

Heimdallr Vertical 6 requires an industrial-grade, bidirectional Email & Account Intelligence subsystem capable of:
1. **Email → Accounts**: Mapping email addresses to online platforms, corporate profiles, and academic registries using non-invasive, permitted evidence.
2. **Identity → Email**: Discovering explicitly supported email addresses from identity handles, person names, phone numbers, and organizations.
3. **Four-Dimensional Email Verification**: Independently evaluating Address Validity (RFC 5322 syntax + DNS MX), Mailbox Deliverability Signals, Identity Association, and Temporal Status (Current vs Stale vs Historical).
4. **Email Identity Resolution**: Disambiguating multiple emails per identity and strictly preventing false merges across individuals sharing names or recycled phone numbers.

In accordance with Heimdallr engineering doctrine, before implementing native capabilities, we audited eleven (11) prominent open-source and hosted candidates across GitHub and PyPI. We inspected actual repositories, codebases, AST structures, network call graphs, and licensing to verify whether README claims held up against runtime reality.

---

### 2. Comprehensive Candidate Inventory & Deep Audit

| Candidate | Claimed Capabilities | Primary Mechanism | Declared License | Maintenance Status | Epistemic Integrity |
|---|---|---|---|---|---|
| **OpenOSINT** | Agentic multi-tool OSINT orchestration | CLI wrapper around Holehe, Maigret, theHarvester via LLM prompt | Apache-2.0 | Moderately maintained | **Low**: Emits hallucinated associations, conflates guessed corporate patterns with verified facts. |
| **Holehe** | 120+ platform account enumeration from email | Password-reset form and account-recovery endpoint probing | GPL-3.0 (Copyleft) | Sporadic maintenance; high platform breakage | **Critical Safety Failure**: Violates CFAA / anti-probing safety constraints; triggers IP rate-limiting and ban lists. |
| **Socialscan** | High-speed email and username platform checking | Unauthenticated public registration API query | MPL-2.0 (Weak Copyleft) | Stale / Unmaintained | **Medium**: Fast and non-invasive, but narrow platform coverage (~15 sites) and brittle endpoints. |
| **theHarvester** | Search engine and public domain scraping | Google, Bing, DuckDuckGo, Baidu web scraping | GPL-2.0 (Copyleft) | Actively maintained | **Low**: High 429 rate-limiting bans, high noise ratio, zero verification of scraped addresses. |
| **Maigret** | 3000+ site username-to-account search | HTTP status / regex profile scraping | MIT | Actively maintained | **Partial**: Excellent for username → URLs, but incapable of bidirectional email discovery or address verification. |
| **SpiderFoot** | Monolithic modular OSINT automation framework | Scrapers, APIs, DNS queries, network probes | MIT | Deprecated / Archived (2023) | **Low**: High dependency bloat (>100 packages), architectural fragility, excessive noise. |
| **h8mail** | Breach data and credential search | HaveIBeenPwned, Dehashed, local breach textfiles | MIT | Unmaintained | **N/A**: Relies on third-party commercial API keys or stale local plaintext breach dumps. |
| **GHunt** | Deep Google account OSINT from Gmail | Google internal API endpoints via user master tokens/cookies | AGPL-3.0 (Viral Copyleft) | Moderately maintained | **Critical Safety & License Failure**: AGPL-3.0 viral contamination, requires user browser session tokens, violates Google ToS. |
| **python-email-validator** | RFC 5322 syntax and DNS MX validation | RFC parsing, `dnspython` MX record resolution | The Unlicense (Public Domain) | Actively maintained | **High**: Ground-truth benchmark for address validity and deliverability prerequisite. |
| **Email-domain-validator** | Corporate domain and throwaway detection | Static disposable email provider blocklists | MIT | Unmaintained | **Medium**: Basic disposable domain blacklist, zero mailbox deliverability or identity signals. |
| **EmailRep** | Email reputation, deliverability, and breach signals | Centralized REST API (Sublime Security) | MIT (Client SDK) / Hosted SaaS | Active | **High**: Excellent reputation signals, but requires external network dependency and API rate budgets. |

---

### 3. Detailed Audit of Evaluated Candidates

#### 3.1 OpenOSINT
- **Repository & Architecture**: An experimental agentic wrapper designed to execute command-line OSINT utilities (including Holehe, Maigret, and theHarvester) via LangChain/LLM planning.
- **Input / Output**: Accepts unstructured investigator queries; outputs raw text summaries and aggregated CLI stdout.
- **Licensing**: Apache-2.0.
- **Runtime Reality vs README**:
  - Transitive execution of copyleft GPL-3.0 dependencies (Holehe) within subprocess invocations.
  - Vulnerable to prompt injection when parsing unverified web documents.
  - Lacks epistemic calibration: outputs guessed corporate email patterns as authoritative findings without corroborating evidence.
- **Verdict**: **REJECT STANDALONE**. Provides useful design ideas for orchestration, but fails strict reliability and security audits.

#### 3.2 Holehe
- **Repository & Architecture**: Python library with over 120 platform modules designed to detect account existence from an email address.
- **Mechanism**: Inspects password-reset forms, forgotten password flows, and login endpoints by issuing simulated recovery requests to check for `"Account exists"` or `"Code sent"` responses.
- **Licensing**: GNU General Public License v3.0 (GPL-3.0).
- **Security & Safety Audit**:
  - **FATAL POLICY VIOLATION**: Probing password-reset endpoints violates Section 5 safety instructions (*"Do not use password-reset probing, unauthorized account enumeration, unsolicited verification messages, or access-control bypasses"*).
  - Triggers Cloudflare challenges, CAPTCHAs, and IP-level blacklisting.
  - Legal and ToS risks under CFAA and computer misuse frameworks.
- **Verdict**: **REJECT & ISOLATE**. Incompatible license (GPL-3.0) and severe operational security hazard.

#### 3.3 Socialscan
- **Repository & Architecture**: Asynchronous Python tool checking whether an email or username is registered on services like GitHub, Twitter/X, Instagram, Spotify, and Yahoo.
- **Mechanism**: Queries publicly accessible registration availability APIs without triggering recovery emails or password resets.
- **Licensing**: Mozilla Public License 2.0 (MPL-2.0).
- **Runtime Reality**:
  - Clean operational paradigm (non-invasive, zero user notification).
  - Out of 15 configured platforms, only ~5 remain functional due to shifting API endpoints and Cloudflare Bot Management.
  - Lacks four-dimensional verification and identity disambiguation.
- **Verdict**: **ADAPT IN CLEAN-ROOM**. Its non-invasive public API registration inspection model is adopted; implementation is rewritten natively to bypass stale third-party dependencies.

#### 3.4 theHarvester
- **Repository & Architecture**: Python OSINT reconnaissance suite searching search engines (Google, Bing, Yahoo), PGP key servers, and Shodan.
- **Mechanism**: Unauthenticated HTML scraping of search results for regex email matches.
- **Licensing**: GPL-2.0.
- **Runtime Reality**:
  - High false positive rate: captures webmaster emails, abuse addresses, and scraping artifacts.
  - Search engines immediately throttle and issue HTTP 429 / CAPTCHAs during automated pipelines.
  - No verification of whether harvested emails are operational or belong to the subject.
- **Verdict**: **REJECT**. GPL-2.0 license contamination and brittle search scraping.

#### 3.5 Maigret
- **Repository & Architecture**: Advanced fork of Sherlock scanning 3,000+ websites for username presence.
- **Mechanism**: HTTP GET/POST against profile URLs checking for HTTP status 200 vs 404 and distinctive DOM selectors.
- **Licensing**: MIT.
- **Runtime Reality**:
  - Highly capable for **Username → Account Profile**.
  - Incapable of **Email → Account** discovery without pre-guessing usernames.
  - Does not evaluate email syntax, MX records, mailbox deliverability, or temporal validity.
- **Verdict**: **COMPLEMENTARY SPECIALIST (RETAINED FOR IDENTITY GRAPH)**. Does not fulfill Vertical 6 email-centric requirements.

#### 3.6 SpiderFoot
- **Repository & Architecture**: Monolithic multi-module OSINT framework with over 200 modules.
- **Licensing**: MIT.
- **Runtime Reality**:
  - Project archived in 2023.
  - High dependency burden (>150 Python packages, SQLite database locking issues).
  - Produces massive uncalibrated noise graphs requiring extensive manual filtering.
- **Verdict**: **REJECT**. Deprecated architecture and unmaintainable footprint.

#### 3.7 GHunt
- **Repository & Architecture**: Specialized Python tool extracting Google public profiles, YouTube channels, Google Maps reviews, Google Calendar IDs, and Gaia IDs from a Gmail address.
- **Mechanism**: Queries undocumented Google internal endpoints using OAuth tokens extracted from a valid user Google account session.
- **Licensing**: GNU Affero General Public License v3.0 (AGPL-3.0).
- **Security & Safety Audit**:
  - **FATAL LICENSE CONTAMINATION**: AGPL-3.0 requires complete open-sourcing of any networked system interacting with it.
  - **OPERATIONAL FRAGILITY**: Requires active maintenance of burner Google cookies (`__Secure-3PAPISID`, etc.), which Google frequently terminates for suspicious automation.
- **Verdict**: **REJECT**. Prohibited AGPL-3.0 license and dependency on compromised session credentials.

#### 3.8 python-email-validator (JoshData)
- **Repository & Architecture**: Standard reference Python library for validating email addresses according to RFC 5321, RFC 5322, RFC 6531, and RFC 6532.
- **Mechanism**: Tokenized grammar parsing, Unicode NFKC canonicalization, Internationalized Domain Names (IDNA) processing, and asynchronous DNS MX record validation via `dnspython`.
- **Licensing**: The Unlicense (Public Domain / MIT compatible).
- **Runtime Reality**:
  - Flawless RFC compliance, zero network scraping, zero safety risk.
  - Accurately rejects invalid syntax, malformed characters, and domains missing MX/A records.
  - Properly bounds its claim: syntax and domain MX validity do *not* imply mailbox deliverability.
- **Verdict**: **RECRUIT FOUNDATIONAL ENGINE**. Integrated directly into `EmailVerificationEngine`.

#### 3.9 EmailRep (Sublime Security)
- **Repository & Architecture**: Reputation and risk scoring engine for email addresses based on social presence, data breaches, domain reputation, deliverability heuristics, and spam traps.
- **Licensing**: MIT client SDK / Hosted REST API.
- **Runtime Reality**:
  - Excellent secondary epistemic signals (e.g., credentials leaked in breaches, domain age, reputation tier).
  - Requires outbound API calls and subscription tokens for production volume.
- **Verdict**: **RECRUIT WITH RESTRICTIONS (OPTIONAL ENRICHMENT PROVIDER)**. Supported as an optional adapter behind capability boundaries.

---

### 4. Summary Findings

None of the open-source candidates alone satisfy all four Vertical 6 requirements without violating licensing, security, or epistemic constraints:
- **Holehe** and **GHunt** are disqualified due to severe security violations (password-reset enumeration) and viral copyleft (GPL-3.0, AGPL-3.0).
- **OpenOSINT** and **theHarvester** hallucinate claims and suffer from brittle search-engine scraping bans.
- **python-email-validator** provides the gold standard for RFC syntax and MX deliverability prerequisites, but provides zero account or identity intelligence.
- **Socialscan** offers the cleanest non-invasive paradigm for platform discovery, but suffers from abandoned platform definitions.

Therefore, the only viable engineering path is **Clean-Room Recruitment & Synthesis**: recruit the permissible, high-integrity algorithms (RFC validation from `python-email-validator`, non-invasive API checking from `Socialscan`, reputation schema from `EmailRep`), insulate them within Heimdallr's Four-Dimensional Epistemic Verifier, and reject all copyleft and dangerous probing tools.
