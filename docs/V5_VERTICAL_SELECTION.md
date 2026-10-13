# Vertical 5 Selection: Onion & Dark-Web Intelligence

**Vertical**: VERTICAL 5 (LOCKED)  
**Domain**: ONION / DARK-WEB INTELLIGENCE  
**Capability Name**: `onion_intelligence`  
**Architectural Policy**: COEXISTENCE & CLEAN-ROOM SPECIALIZATION  
**Status**: VALIDATED & BENCHMARKED  

---

## 1. Executive Summary & Objective

In accordance with architectural directives, **Vertical 5 is locked as ONION / DARK-WEB INTELLIGENCE**. Under no circumstances is the recruitment engineer permitted to deviate into Financial, Social, Cloud, Email, Technology, or News verticals.

The primary objective of this recruitment cycle is to determine whether Heimdallr requires a dedicated **Onion Intelligence** capability, evaluate the open-source landscape (auditing **Ahmia**, **TorBot**, and relevant ecosystem alternatives), establish legal and security boundaries, construct a frozen 100-task causal benchmark suite, and formulate an evidence-backed architectural decision.

Benchmark evidence determines survival. Neither the incumbent (Argus Generalist) nor candidates (Ahmia, TorBot) enjoy automatic approval.

---

## 2. The Capability Gap in Heimdallr

Prior to Vertical 5, Heimdallr possessed specialists in:
1. `general_web_research` (Argus broad open-web crawling and document ingestion)
2. `identity_resolution` (Developer persona mapping, handles, Keybase/PGP)
3. `infrastructure_discovery` (DNS zone records, CT logs, BGP routing, mailhosts)
4. `corporate_registry_intelligence` (Companies House, Delaware, commercial registries)
5. `sanctions_and_beneficial_ownership` (OFAC SDN, consolidated lists, offshore leaks)

### The Blind Spot: The Hidden Onion Layer
Generalist web scrapers and clearnet search engines cannot:
- Resolve `.onion` v3 cryptographic hidden service descriptors via Tor distributed hash tables (DHT).
- Negotiate rendezvous points and SOCKS5 proxy circuits to access public Tor hidden services.
- Search darknet hidden service indexes for unindexed data extortion portals (e.g., ALPHV, LockBit, CL0P).
- Crawl recursive onion link trees while parsing Monero/Bitcoin extortion addresses and PGP signatures.
- Differentiate authentic hidden service mirrors from adversarial phishing clones.

On the 100-task frozen benchmark suite:
- **Argus Generalist Baseline passed only 15/100 tasks (15.0%)**, succeeding only on negative tasks (NOT_FOUND and UNKNOWN) where no onion data existed. On every task requiring hidden service discovery, darknet extortion parsing, or onion crawling, Argus failed completely (0.0% entity recall, 0.0% claim recall).

This demonstrates that **Onion & Dark-Web Intelligence is a genuine, structural capability gap in Heimdallr**.

---

## 3. Scope and Ethical/Legal Boundary

Heimdallr is built exclusively for public-information intelligence, defensive threat intelligence, corporate risk mitigation, and security research.

### Permitted Capabilities:
- Onion service discovery (mapping public `.onion` addresses).
- Indexed darknet search and discovery (Ahmia model).
- Recursive crawling of public onion landing pages and link topology (TorBot model).
- Cryptographic identifier extraction (Bitcoin, Monero, PGP fingerprints, XMPP/Tox handles).
- Mirror clustering and authenticity verification (detecting phishing duplicates).
- Temporal presence tracking (first-seen, last-seen, seizure notice detection).
- Contradiction resolution between extortion disclosures and clearnet corporate statements.

### Strict Non-Goals & Prohibitions:
In compliance with Section 23 of the recruitment protocol:
- **NO credential theft or harvesting**.
- **NO unauthorized access or private network intrusion**.
- **NO exploit delivery or payload execution**.
- **NO persistence mechanisms**.
- **NO deanonymization or traffic correlation attacks against innocent Tor users**.
- **NO CAPTCHA bypass or anti-bot circumvention on private systems**.
- **NO targeting of individuals for surveillance or harassment**.

---

## 4. Architectural Integration Model

Untrusted dark-web text is **DATA, NOT INSTRUCTIONS**.

The Onion Intelligence specialist does **not** create authoritative state directly. All specialist outputs are:
1. Captured as unprivileged `NormalizedObservation` records (`is_authoritative = False`).
2. Sanitized through the centralized `SecurityGateValidator` to strip shell commands, prompt injections, and path traversal strings.
3. Passed through Heimdallr's existing Verifier pipeline:
   $$\text{Specialist Observation} \longrightarrow \text{Security Gate} \longrightarrow \text{Verifier} \longrightarrow \text{Epistemic Model} \longrightarrow \text{Authoritative State}$$

This guarantees total isolation of authoritative truth while providing first-class dark-web intelligence.
