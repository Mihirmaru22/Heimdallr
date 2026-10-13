# Vertical 5 Capability Specification: Onion Intelligence

**Capability ID**: `onion_intelligence`  
**Category**: `ONION_AND_DARKWEB`  
**Version**: `1.0.0`  
**Provider**: `argus.specialists.onion`  
**Status**: `AVAILABLE`  

---

## 1. Capability Overview

The `onion_intelligence` capability provides autonomous discovery, indexed search, recursive crawling, cryptographic identifier extraction, and mirror clustering across Tor hidden services (`.onion` v3).

It strictly decouples the abstract **CAPABILITY** from concrete **IMPLEMENTATIONS**, enabling dynamic routing and selection between specialized search providers (Ahmia), deep crawler engines (TorBot clean-room), or unified coexistence adapters.

---

## 2. Question Types Supported

The capability processes 12 primary investigation question types:
1. `ONION_SERVICE_DISCOVERY`: Discover active `.onion` addresses for known threat actors, extortion portals, or forums.
2. `ONION_SEARCH`: Query indexed darknet repositories for victim breach disclosures, stolen source code, or threat discussions.
3. `ONION_CRAWLING`: Recursively crawl hidden services, extract internal link structures, and catalog subpages.
4. `ONION_ENTITY_DISCOVERY`: Extract cryptographic wallet addresses (BTC, XMR, ETH), PGP keys, and contact handles (XMPP, Tox, SimpleX).
5. `ONION_ENTITY_RESOLUTION`: Disambiguate darknet operator personas and map threat actor lineages (e.g., ALPHV to BlackCat/DarkSide).
6. `ONION_HISTORY`: Retrieve historical service availability, seizure records, and first/last-seen timestamps.
7. `ONION_SOURCE_VERIFICATION`: Verify cryptographic authenticity of mirrors, detecting fraudulent phishing clones.
8. `ONION_RELATIONSHIP_DISCOVERY`: Connect onion services to upstream C2 infrastructure, clearnet mirrors, or beneficial owners.
9. `ONION_MULTI_HOP`: Cross-domain reasoning bridging onion intelligence with Corporate, Sanctions, Infrastructure, and Identity specialists.
10. `ONION_NOT_FOUND`: Definitively confirm absence of dark-web exposure for non-compromised entities.
11. `DARKWEB_INTELLIGENCE`: General defensive inquiry targeting hidden services.
12. `TOR_INVESTIGATION`: Protocol-aware hidden service descriptor exploration.

---

## 3. Input & Output Contracts

### Input Schema (`CapabilityInputSchema`)
```json
{
  "type": "object",
  "required": ["query"],
  "properties": {
    "query": {
      "type": "string",
      "description": "Natural language inquiry, target entity name, or .onion URL"
    },
    "target_entity": {
      "type": "string",
      "description": "Target organization, threat syndicate, or persona"
    },
    "onion_address": {
      "type": "string",
      "description": "Specific .onion v3 address (56 characters)"
    },
    "max_depth": {
      "type": "integer",
      "default": 1,
      "description": "Recursive crawl depth limit (bounded to prevent resource exhaustion)"
    }
  }
}
```

### Output Schema (`CapabilityOutputSchema`)
```json
{
  "type": "object",
  "properties": {
    "services": {
      "type": "array",
      "description": "Discovered Tor hidden service descriptors with status and timestamps"
    },
    "pages": {
      "type": "array",
      "description": "Crawled page snapshots, titles, and text snippets"
    },
    "crypto_addresses": {
      "type": "object",
      "description": "Extracted cryptocurrency addresses categorized by asset (BTC, XMR, ETH)"
    },
    "pgp_fingerprints": {
      "type": "array",
      "description": "ASCII-armored PGP key fingerprints"
    },
    "contact_identities": {
      "type": "array",
      "description": "Discovered communication handles (XMPP, Jabber, Tox, SimpleX)"
    },
    "mirrors": {
      "type": "object",
      "description": "Verified official mirrors vs detected phishing clones"
    }
  },
  "epistemic_nature": "OBSERVATION",
  "authoritative": false
}
```

---

## 4. Evidence Requirements & Declared Types

To drive deterministic routing via `CapabilityMatcher`, the capability declares 19 canonical evidence types:
- `ONION_SERVICE_DESCRIPTOR`
- `ONION_INDEX_RECORD`
- `ONION_CRAWL_SNAPSHOT`
- `ONION_EXTRACTED_ENTITY`
- `ONION_RELATIONSHIP_RECORD`
- `ONION_HISTORICAL_ARCHIVE`
- `ONION_MIRROR_CLUSTER`
- `DARKWEB_LEAK_PORTAL_POSTING`
- `ONION_CRAWLER_TOPOLOGY`
- `DARKNET_FORUM_THREAD`
- `ONION_CRYPTOCURRENCY_WALLET`
- `ONION_PGP_KEY_BLOCK`
- `ONION_CONTACT_HANDLE`
- `DARK_WEB_CONTACT_HANDLE`
- `DARK_WEB_PASTE_SNIPPET`
- `DARK_WEB_EXTRACTED_ENTITY`
- `ONION_EXPLOIT_PROOF`
- `ONION_WHISTLEBLOWER_PAYLOAD`
- `ONION_DEPOSIT_ENDPOINT`
- `TOR_HIDDEN_SERVICE_PAYLOAD`
- `DARKWEB_CREDENTIAL_LISTING`
- `ONION_MIRROR_FINGERPRINT`

---

## 5. Epistemic Behavior & Invariants

1. **Observations are NOT Authoritative**: All specialist outputs are delivered as `NormalizedObservation` records where `is_authoritative = False` and `epistemic_status = "OBSERVED_DARKWEB_DESCRIPTOR"`.
2. **Mandatory Verifier Pipeline**: Raw claims regarding corporate breaches or extortion demands remain `UNVERIFIED` until corroborated by independent primary evidence (e.g., sample file tree hashes, SEC 8-K disclosures, or cryptographic key matches).
3. **Temporal Distinction**:
   - `ACTIVE`: Service responds to SOCKS5 rendezvous circuit handshake.
   - `SEIZED`: Law enforcement seizure notice displayed.
   - `DEGRADED`: Service rate-limiting or requiring proof-of-work.
   - `HISTORICAL`: Found in archived search index; currently unreachable.
   - `NOT_FOUND`: Hidden service descriptor not found in DHT.
   *A service being currently offline does NOT mean it never existed.*
4. **Contradiction Resolution**:
   - Compares PGP signatures and server TLS certificates across mirrors.
   - Resolves extortion claims vs corporate PR using sample data verification and provenance weighting.

---

## 6. Implementation Selection Criteria

`ImplementationSelector` dynamically ranks registered implementations for `onion_intelligence` based on:
1. **Capability Category & Health**: HealthStatus must be `AVAILABLE` or `DEGRADED` (UNAVAILABLE, DISABLED, QUARANTINED excluded).
2. **Benchmark Performance**: F1 score and evidence correctness from frozen benchmarks.
3. **Licensing Compatibility**: Must be permissive (`APPROVED` under Apache-2.0, MIT, BSD). Copyleft GPL code is strictly excluded.
4. **Sub-Capability Match**:
   - Keyword search across index $\rightarrow$ select Ahmia engine.
   - Link traversal, crypto extraction, or mirror cluster tracing $\rightarrow$ select TorBot clean-room engine.
   - Full end-to-end investigation $\rightarrow$ select Unified Coexistence engine (`impl_onion_integrated_v1`).
