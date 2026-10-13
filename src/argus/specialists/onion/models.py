"""Heimdallr V5: Onion & Dark-Web Intelligence Data Models.

Defines strongly-typed representations for Tor hidden services, crawled pages,
extracted cryptographic identifiers, mirror clusters, and temporal presence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OnionServiceStatus(str, Enum):
    """Reachability and lifecycle state of a Tor hidden service."""

    ACTIVE = "ACTIVE"
    HISTORICAL_OFFLINE = "HISTORICAL_OFFLINE"
    SEIZED = "SEIZED"
    DEFACED = "DEFACED"
    UNVERIFIED = "UNVERIFIED"
    UNKNOWN = "UNKNOWN"
    NOT_FOUND = "NOT_FOUND"


class OnionService(BaseModel):
    """Normalized metadata for a Tor .onion hidden service (v3 or legacy v2)."""

    onion_address: str = Field(..., description="Canonical .onion address")
    service_name: str = Field(..., description="Human-readable title or service name")
    category: str = Field(..., description="Intelligence category (LEAK_SITE, FORUM, MARKET, ESCROW, REPO)")
    description: str = Field(default="", description="Service synopsis or extracted text description")
    first_seen: Optional[str] = Field(default=None, description="ISO timestamp when first indexed")
    last_seen: Optional[str] = Field(default=None, description="ISO timestamp when last observed active")
    status: OnionServiceStatus = Field(default=OnionServiceStatus.ACTIVE)
    mirrors: List[str] = Field(default_factory=list, description="Associated alternate .onion mirrors")
    clearnet_domains: List[str] = Field(default_factory=list, description="Linked or claimed clearnet websites")
    associated_entities: List[str] = Field(default_factory=list, description="Linked organizations, threat groups, or individuals")
    crypto_addresses: Dict[str, List[str]] = Field(default_factory=dict, description="Cryptocurrency addresses (BTC, XMR)")
    contact_identities: List[str] = Field(default_factory=list, description="Emails, Jabber/XMPP, PGP key fingerprints")
    pgp_fingerprints: List[str] = Field(default_factory=list, description="Published PGP signing key fingerprints")
    server_fingerprint: Optional[str] = Field(default=None, description="HTTP header, TLS/cert, or daemon fingerprint")
    indexed_pages_count: int = Field(default=1)
    is_malicious_decoy: bool = Field(default=False, description="Whether this service is a phishing clone or honeypot")


class OnionPage(BaseModel):
    """A crawled page within a Tor hidden service."""

    url: str
    onion_address: str
    path: str
    title: str
    raw_content: str
    extracted_text: str
    links_out: List[str] = Field(default_factory=list)
    extracted_entities: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    has_hostile_content: bool = False


class OnionObservationPayload(BaseModel):
    """Normalized payload emitted by Onion capability implementations."""

    query: str
    operation: str
    services_found: List[OnionService] = Field(default_factory=list)
    pages_found: List[OnionPage] = Field(default_factory=list)
    extracted_crypto: Dict[str, List[str]] = Field(default_factory=dict)
    extracted_pgp: List[str] = Field(default_factory=list)
    extracted_identities: List[str] = Field(default_factory=list)
    mirror_clusters: List[Dict[str, Any]] = Field(default_factory=list)
    temporal_status: str = "CURRENT"
    epistemic_status: str = "OBSERVED_UNVERIFIED_SOURCE"
    is_authoritative: bool = False
