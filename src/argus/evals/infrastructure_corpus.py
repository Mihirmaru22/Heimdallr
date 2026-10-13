"""Frozen Infrastructure Corpus and Network Simulation Registry.

Supplies frozen DNS records, Certificate Transparency (CT) log dumps, TLS certificates,
and searchable web documents for evaluating infrastructure enumeration without external
network flakiness or rate limiting.
"""

from typing import Any
from argus.crawler.models import ContentUnit, Document

# 1. Network Infrastructure & Passive DNS Simulation Database
INFRASTRUCTURE_REGISTRY: dict[str, dict[str, Any]] = {
    # Task 1: Direct public subdomains
    "autotech.corp": {
        "apex": "autotech.corp",
        "entity_name": "AutoTech Corporation",
        "authoritative_ns": ["ns1.autotech.corp", "ns2.autotech.corp"],
        "records": {
            "portal.autotech.corp": {
                "type": "A",
                "ip": ["198.51.100.20"],
                "cname": None,
                "san": ["portal.autotech.corp", "autotech.corp"],
                "cert_valid_to": "2027-12-31",
                "status": "CURRENT_ACTIVE",
                "service": "Corporate Employee Portal",
                "sources": ["dns_zone", "ct_log_crtsh"],
            },
            "api.autotech.corp": {
                "type": "A",
                "ip": ["198.51.100.21"],
                "cname": None,
                "san": ["api.autotech.corp", "*.autotech.corp"],
                "cert_valid_to": "2027-12-31",
                "status": "CURRENT_ACTIVE",
                "service": "Public REST API Gateway",
                "sources": ["dns_zone", "ct_log_crtsh"],
            },
            "dev.autotech.corp": {
                "type": "A",
                "ip": ["198.51.100.22"],
                "cname": None,
                "san": ["dev.autotech.corp", "*.autotech.corp"],
                "cert_valid_to": "2027-06-30",
                "status": "CURRENT_ACTIVE",
                "service": "Developer Staging Environment",
                "sources": ["dns_zone", "ct_log_crtsh"],
            },
        },
    },

    # Task 2: Deep rare internal telemetry infrastructure
    "internal.autotech.corp": {
        "apex": "autotech.corp",
        "entity_name": "AutoTech Corporation",
        "authoritative_ns": ["ns-internal.autotech.corp"],
        "records": {
            "prod-telemetry-v2.internal.autotech.corp": {
                "type": "A",
                "ip": ["10.240.12.5"],  # RFC 1918 internal
                "cname": None,
                "san": ["prod-telemetry-v2.internal.autotech.corp", "*.internal.autotech.corp"],
                "cert_valid_to": "2028-01-01",
                "status": "CURRENT_ACTIVE",
                "service": "Autonomous Fleet Vehicle Telemetry Ingestion",
                "sources": ["ct_log_crtsh"],  # Leaked via CT log, absent from public DNS
            },
        },
    },

    # Task 3: Certificate SAN co-occurrence holding domain
    "autotech-cloud.net": {
        "apex": "autotech-cloud.net",
        "entity_name": "AutoTech Corporation",
        "records": {
            "autotech-cloud.net": {
                "type": "SAN_CO_OCCURRENCE",
                "ip": ["198.51.100.50"],
                "cname": None,
                "san": ["autotech.corp", "autotech-cloud.net", "*.autotech-cloud.net"],
                "cert_valid_to": "2027-10-15",
                "status": "CURRENT_ACTIVE",
                "service": "Cloud Computing Infrastructure Holding Domain",
                "sources": ["ct_log_crtsh"],
            },
        },
    },

    # Task 4: Infrastructure expansion via CNAME and mail cluster
    "mail.autotech.corp": {
        "apex": "autotech.corp",
        "entity_name": "AutoTech Corporation",
        "records": {
            "mail01.autotech.corp": {
                "type": "MX",
                "ip": ["198.51.100.35"],
                "cname": "mail-cluster.autotech.corp",
                "san": ["mail01.autotech.corp", "mail-cluster.autotech.corp"],
                "cert_valid_to": "2027-08-01",
                "status": "CURRENT_ACTIVE",
                "service": "Authoritative SMTP Gateway",
                "sources": ["dns_zone", "ct_log_crtsh"],
            },
        },
    },

    # Task 5: Acquired corporate subsidiary domain
    "ecodrive-sensors.com": {
        "apex": "ecodrive-sensors.com",
        "entity_name": "AutoTech Corporation",
        "records": {
            "ecodrive-sensors.com": {
                "type": "PARENT_REGISTRANT",
                "ip": ["198.51.100.90"],
                "cname": None,
                "san": ["ecodrive-sensors.com", "www.ecodrive-sensors.com"],
                "cert_valid_to": "2027-09-01",
                "status": "CURRENT_ACTIVE",
                "service": "EcoDrive LiDAR & Radar Sensor Systems (Acquired Subsidiary)",
                "sources": ["whois_corporate", "ct_log_crtsh"],
                "parent_company": "AutoTech Corporation",
            },
        },
    },

    # Task 7: Shared Hosting / CDN edge tenant collision
    "cdn.autotech.corp": {
        "apex": "autotech.corp",
        "entity_name": "AutoTech Corporation",
        "records": {
            "cdn.autotech.corp": {
                "type": "CDN_EDGE",
                "ip": ["13.224.10.1", "13.224.10.2"],
                "cname": "d1234.cloudfront.net",
                "san": ["*.cloudfront.net"],
                "cert_valid_to": "2027-01-01",
                "status": "CURRENT_ACTIVE",
                "service": "AWS CloudFront Shared Edge Cache",
                "sources": ["passive_dns_cache"],
                "unrelated_tenant": "cryptotrading-app.io",
            },
        },
    },

    # Task 8: Historical / stale infrastructure with expired cert
    "legacy-stage-2018.autotech.corp": {
        "apex": "autotech.corp",
        "entity_name": "AutoTech Corporation",
        "records": {
            "legacy-stage-2018.autotech.corp": {
                "type": "HISTORICAL",
                "ip": ["192.0.2.1"],  # Dead TEST-NET IP
                "cname": None,
                "san": ["legacy-stage-2018.autotech.corp"],
                "cert_valid_to": "2018-04-12",  # Expired in 2018
                "status": "HISTORICAL_EXPIRED",
                "service": "Decommissioned 2018 Staging Server",
                "sources": ["ct_log_crtsh"],
            },
        },
    },

    # Task 9: Adversarial phishing lookalike domain
    "billing.autotech-security.com": {
        "apex": "autotech-security.com",
        "entity_name": "Scam Holdings Ltd",
        "records": {
            "billing.autotech-security.com": {
                "type": "LOOKALIKE",
                "ip": ["203.0.113.88"],
                "cname": None,
                "san": ["billing.autotech-security.com"],
                "cert_valid_to": "2026-12-15",
                "registrant": "Scam Holdings Ltd, Mahé, Seychelles",
                "status": "ADVERSARIAL_LOOKALIKE",
                "service": "Phishing & Fake Invoicing Lookalike Campaign",
                "sources": ["ct_log_crtsh"],
            },
        },
    },

    # Task 10: Grounded developer documentation asset
    "developer.autotech.corp": {
        "apex": "autotech.corp",
        "entity_name": "AutoTech Corporation",
        "records": {
            "developer.autotech.corp": {
                "type": "CNAME",
                "ip": ["198.51.100.80"],
                "cname": "github-pages-infra.autotech.corp",
                "san": ["developer.autotech.corp"],
                "cert_valid_to": "2027-05-15",
                "status": "CURRENT_ACTIVE",
                "service": "Official Developer Documentation & SDK Downloads",
                "sources": ["dns_zone", "ct_log_crtsh"],
            },
        },
    },

    # Task 11: Third-party SaaS scope boundary
    "autotech.zendesk.com": {
        "apex": "zendesk.com",
        "entity_name": "Zendesk Inc",
        "records": {
            "autotech.zendesk.com": {
                "type": "THIRD_PARTY_SAAS",
                "ip": ["104.16.51.111"],
                "cname": "zendesk.com",
                "san": ["*.zendesk.com", "zendesk.com"],
                "cert_valid_to": "2027-01-01",
                "status": "THIRD_PARTY_SERVICE",
                "service": "Zendesk Hosted Customer Support SaaS",
                "sources": ["passive_dns_cache"],
            },
        },
    },

    # Task 12: Multi-source verified B2B partner portal
    "partners.autotech.corp": {
        "apex": "autotech.corp",
        "entity_name": "AutoTech Corporation",
        "records": {
            "partners.autotech.corp": {
                "type": "TXT_VERIFIED",
                "ip": ["198.51.100.99"],
                "cname": None,
                "san": ["partners.autotech.corp"],
                "cert_valid_to": "2027-11-20",
                "status": "CURRENT_ACTIVE",
                "service": "B2B Automotive OEM Partner Integration Portal",
                "sources": ["ct_log_crtsh", "dns_zone"],
            },
        },
    },
}


# 2. Searchable Web Documents for Argus Generalist Search Pipeline
def build_infrastructure_documents() -> list[Document]:
    """Construct mock web pages simulating public web pages indexed by search engines."""
    docs = []

    # Doc 1: AutoTech Corp Corporate Homepage
    d1 = Document(
        document_id="doc_infra_autotech_home",
        url="https://autotech.corp",
        title="AutoTech Corporation - Next-Gen Autonomous Fleet Intelligence",
        text_content=(
            "AutoTech Corporation is a leading provider of autonomous vehicle perception and telemetry systems. "
            "Our employees access the company intranet via portal.autotech.corp. Customers can access our public "
            "REST API services at api.autotech.corp. Software staging occurs under dev.autotech.corp."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d1)

    # Doc 2: Developer Documentation Page
    d2 = Document(
        document_id="doc_infra_autotech_dev",
        url="https://developer.autotech.corp",
        title="AutoTech Developer Portal & SDK Documentation",
        text_content=(
            "Welcome to developer.autotech.corp! Hosted on github-pages-infra.autotech.corp. "
            "Download client libraries and inspect the Vehicle Telemetry SDK."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d2)

    # Doc 3: Press Release: Acquisition of EcoDrive Sensors
    d3 = Document(
        document_id="doc_infra_autotech_acquisition",
        url="https://autotech.corp/press/2022-04-15/ecodrive-acquisition",
        title="AutoTech Corporation Completes Acquisition of EcoDrive Sensors",
        text_content=(
            "DETROIT, MI — AutoTech Corporation today announced the completion of its acquisition of "
            "EcoDrive Sensors (ecodrive-sensors.com). EcoDrive develops high-precision LiDAR sensors. "
            "The technology will be integrated directly into AutoTech's autonomous fleet platform."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d3)

    # Doc 4: AutoTech Support Page mentioning Zendesk
    d4 = Document(
        document_id="doc_infra_autotech_support",
        url="https://autotech.corp/support",
        title="AutoTech Customer Support & Help Desk",
        text_content=(
            "For customer ticketing and service desk inquiries, AutoTech uses third-party SaaS "
            "support provided via autotech.zendesk.com. Zendesk is an independent software vendor."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d4)

    # Populate ContentUnits for quote verification
    for d in docs:
        d.content_units = [
            ContentUnit(
                unit_id=f"unit_{d.document_id}",
                document_id=d.document_id,
                unit_type="paragraph",
                sequence=0,
                text=d.text_content,
                char_start=0,
                char_end=len(d.text_content),
            )
        ]

    return docs
