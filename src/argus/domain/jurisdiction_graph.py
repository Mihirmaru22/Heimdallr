"""Jurisdiction-Aware Entity Graph for Cross-Border Corporate OSINT.

Explicitly represents:
Entity
├── jurisdiction (e.g. US, GB, DE, IN, KY)
├── legal identifier (e.g. CIK, CRN, LEI, HRB)
├── parent
├── subsidiaries
├── effective dates
├── source registry (e.g. SEC EDGAR, Companies House, Handelsregister)
└── confidence

Enforces the critical disambiguation invariant:
Same name in different jurisdictions != Same legal entity!
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JurisdictionEntityNode(BaseModel):
    """An individual legally distinct corporate or natural entity anchored to a jurisdiction."""

    node_id: str
    canonical_name: str
    jurisdiction: str = Field(..., description="ISO 3166-1 alpha-2 or standard jurisdiction code (e.g. US-DE, GB, DE, KY)")
    legal_identifier: str | None = Field(default=None, description="Official registry ID (CRN, CIK, LEI, etc.)")
    source_registry: str = Field(..., description="Official registrar (e.g. Companies House, SEC EDGAR)")
    parent_id: str | None = None
    subsidiary_ids: list[str] = Field(default_factory=list)
    effective_start_date: str | None = None
    effective_end_date: str | None = None
    is_active: bool = True
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    attributes: dict[str, Any] = Field(default_factory=dict)


class JurisdictionEntityGraph:
    """Graph of jurisdictionally anchored corporate entities and their control relationships."""

    def __init__(self) -> None:
        self.nodes: dict[str, JurisdictionEntityNode] = {}
        # Mapping from (canonical_name_lower, jurisdiction_lower) -> node_id
        self._name_jurisdiction_index: dict[tuple[str, str], str] = {}
        # Mapping from canonical_name_lower -> list of node_ids across jurisdictions
        self._name_index: dict[str, list[str]] = {}

    def register_entity(
        self,
        name: str,
        jurisdiction: str,
        source_registry: str,
        legal_identifier: str | None = None,
        parent_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        confidence: float = 1.0,
    ) -> JurisdictionEntityNode:
        """Registers a verified entity anchored to its legal jurisdiction."""
        clean_name = name.strip()
        norm_name = clean_name.lower()
        norm_jur = jurisdiction.strip().upper()
        node_id = f"{norm_jur}_{norm_name.replace(' ', '_')}"

        if node_id in self.nodes:
            node = self.nodes[node_id]
            if legal_identifier and not node.legal_identifier:
                node.legal_identifier = legal_identifier
            if parent_id and not node.parent_id:
                node.parent_id = parent_id
            return node

        node = JurisdictionEntityNode(
            node_id=node_id,
            canonical_name=clean_name,
            jurisdiction=norm_jur,
            legal_identifier=legal_identifier,
            source_registry=source_registry,
            parent_id=parent_id,
            effective_start_date=start_date,
            effective_end_date=end_date,
            confidence=confidence,
        )

        self.nodes[node_id] = node
        self._name_jurisdiction_index[(norm_name, norm_jur)] = node_id

        if norm_name not in self._name_index:
            self._name_index[norm_name] = []
        self._name_index[norm_name].append(node_id)

        # Update parent's subsidiary list
        if parent_id and parent_id in self.nodes:
            if node_id not in self.nodes[parent_id].subsidiary_ids:
                self.nodes[parent_id].subsidiary_ids.append(node_id)

        return node

    def link_parent_subsidiary(self, parent_id: str, subsidiary_id: str) -> None:
        """Explicitly connects cross-border parent to subsidiary without conflating identities."""
        if parent_id in self.nodes and subsidiary_id in self.nodes:
            self.nodes[subsidiary_id].parent_id = parent_id
            if subsidiary_id not in self.nodes[parent_id].subsidiary_ids:
                self.nodes[parent_id].subsidiary_ids.append(subsidiary_id)

    def resolve_entity(
        self,
        name: str,
        target_jurisdiction: str | None = None,
    ) -> list[JurisdictionEntityNode]:
        """Resolves an entity name, distinguishing distinct legal entities across jurisdictions."""
        norm_name = name.strip().lower()

        if target_jurisdiction:
            norm_jur = target_jurisdiction.strip().upper()
            node_id = self._name_jurisdiction_index.get((norm_name, norm_jur))
            if node_id:
                return [self.nodes[node_id]]

        node_ids = self._name_index.get(norm_name, [])
        return [self.nodes[nid] for nid in node_ids]

    def are_same_legal_entity(self, name_a: str, jur_a: str, name_b: str, jur_b: str) -> bool:
        """Verifies whether two entity references refer to the exact same legal entity."""
        if jur_a.strip().upper() != jur_b.strip().upper():
            # Different jurisdictions mean distinct legal entities (even if names are identical)
            return False
        return name_a.strip().lower() == name_b.strip().lower()

    def get_affiliate_hierarchy(self, root_id: str) -> list[JurisdictionEntityNode]:
        """Traverses parent-subsidiary hierarchy across jurisdictions."""
        hierarchy = []
        queue = [root_id]
        visited = set()

        while queue:
            curr_id = queue.pop(0)
            if curr_id in visited or curr_id not in self.nodes:
                continue
            visited.add(curr_id)
            node = self.nodes[curr_id]
            hierarchy.append(node)
            for sub_id in node.subsidiary_ids:
                if sub_id not in visited:
                    queue.append(sub_id)

        return hierarchy
