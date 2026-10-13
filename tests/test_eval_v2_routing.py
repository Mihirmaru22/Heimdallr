"""Tests for Eval V2 specialist routing classifier and harness."""

import pytest
from argus.evals.v2.models import SpecialistType
from argus.evals.v2.routing_evaluator import SpecialistRoutingClassifier, RoutingHarness


def test_routing_classifier_domains():
    router = SpecialistRoutingClassifier()

    # Corporate query
    res_corp = router.route("Find SEC 10-K filings, CIK code, and subsidiaries for AeroDynamics")
    assert SpecialistType.CORPORATE in res_corp
    assert SpecialistType.INFRASTRUCTURE not in res_corp

    # Infrastructure query
    res_infra = router.route("Enumerate DNS records, MX hostnames, and TLS certificate SANs for example.com")
    assert SpecialistType.INFRASTRUCTURE in res_infra
    assert SpecialistType.CORPORATE not in res_infra

    # Identity query
    res_ident = router.route("Map GitHub commit history and developer screen name for user_123")
    assert SpecialistType.IDENTITY in res_ident
    assert SpecialistType.CORPORATE not in res_ident

    # General query (Bypass)
    res_gen = router.route("Summarize quantum computing principles from academic papers")
    assert res_gen == [SpecialistType.NONE]


def test_routing_classifier_multi_specialist():
    router = SpecialistRoutingClassifier()

    # Cross-specialist query: Corporate + Infrastructure
    res_multi = router.route("Locate UK subsidiary filings for AeroDynamics and check its domain DNS zone records")
    assert SpecialistType.CORPORATE in res_multi
    assert SpecialistType.INFRASTRUCTURE in res_multi
