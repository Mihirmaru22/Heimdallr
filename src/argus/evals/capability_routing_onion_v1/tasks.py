"""Heimdallr V5: CAPABILITY_ROUTING_ONION_V1 Tasks.

100 frozen routing tasks (50 positive dark-web/onion tasks, 50 negative non-onion tasks).
Evaluates CapabilityMatcher and ImplementationSelector.
Strictly isolates evaluation labels: no capability IDs or ground-truth names are in task inputs.
"""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class OnionRoutingTask(BaseModel):
    task_id: str
    query: str
    evidence_requirements: List[str]
    # Ground-truth labels evaluated exclusively by grader, never passed into matcher inputs:
    expected_capabilities_evaluator_only: List[str] = Field(default_factory=list)
    is_onion_positive: bool = False


def build_routing_onion_v1_tasks() -> List[OnionRoutingTask]:
    """Generate 100 frozen routing tasks (50 positive, 50 negative)."""
    tasks: List[OnionRoutingTask] = []

    # =========================================================================
    # POSITIVE TASKS (50 Tasks: Dark-Web, Onion Services, Crawling, Extortion)
    # =========================================================================
    pos_specs = [
        ("Discover active onion address for ALPHV BlackCat data leak portal.", ["Tor hidden service onion descriptor and published victim index"]),
        ("Search dark web for compromised source code belonging to Apex Technologies.", ["Dark-web extortion portal posting and sample file archives"]),
        ("Crawl LockBit 3.0 hidden service to map internal subpages and mirrors.", ["Onion crawler topology graph and internal link tree"]),
        ("Extract cryptocurrency ransom payment addresses from darknet leak site.", ["Extracted Bitcoin and Monero wallet strings from hidden service HTML"]),
        ("Discover Tor v3 service where CL0P syndicate posts corporate torrent archives.", ["Tor v3 onion address and P2P distribution archive listing"]),
        ("Locate official Tor hidden service for Dread darknet discussion forum.", ["Darknet forum onion descriptor and authenticated index listing"]),
        ("Extract PGP public key fingerprint for darknet forum administrator.", ["ASCII armored PGP key block extracted from onion admin profile"]),
        ("Search dark web forums for exploit discussion concerning MOVEit vulnerability.", ["Indexed darknet forum discussion thread matching CVE-2023-34362"]),
        ("Crawl Sandworm C2 hidden service to extract operational relay descriptors.", ["Tor hidden service descriptor matching GRU military relay infrastructure"]),
        ("Discover darknet cryptocurrency escrow portal operated by Lazarus Group.", ["Tor onion escrow service descriptor and multi-sig deposit endpoints"]),
        ("Verify whether dark-web mirror is an authentic clone or phishing imposter.", ["Cryptographic PGP signature verification and mirror fingerprint comparison"]),
        ("Search Tor hidden services for leaked defense contractor telemetry.", ["Dark-web archive cache index matching aerospace contractor files"]),
        ("Extract contact handles (Tox, XMPP, Jabber) from extortion syndicate portal.", ["Negotiator contact strings extracted from Tor leak site header"]),
        ("Crawl Altai Shadow Holding onion portal to catalog private document repositories.", ["Onion site directory crawl and maritime shipping manifest files"]),
        ("Investigate dark web publication of stolen medical patient database.", ["Darknet marketplace or leak blog entry containing patient records"]),
        ("Search onion index for database breaches involving municipal water utility.", ["Indexed dark-web leak cache mentioning municipal infrastructure"]),
        ("Discover hidden service address for Freedom Press SecureDrop intake.", ["Whistleblower intake onion address and TLS certificate fingerprint"]),
        ("Extract Monero donation address from decentralized Tor cybercrime community.", ["Regex-validated Monero address from darknet community landing page"]),
        ("Crawl dark-web hacker collective portal to catalog released exploit tools.", ["Crawl tree of onion directory hosting exploit proof-of-concepts"]),
        ("Search dark-web search engine Ahmia for mentions of Orion Defense Systems.", ["Ahmia Tor search engine indexed page results"]),
        ("Verify historical availability and downtime history of seized darknet market.", ["Historical onion uptime records and law enforcement seizure banner logs"]),
        ("Extract Ethereum smart-contract address embedded in darknet money mixer.", ["Hexadecimal Ethereum contract address extracted from onion mixer UI"]),
        ("Crawl private Tor discussion forum to identify active credential seller threads.", ["Forum thread listing extracted via bounded recursive onion crawler"]),
        ("Locate onion mirror clusters associated with LockBit ransomware operation.", ["Mirror cluster enumeration and canonical onion domain resolution"]),
        ("Search dark-web breach forums for corporate credentials belonging to fintech firm.", ["Dark-web credential market listing and combo list sample"]),
        ("Extract PGP signature from darknet vendor profile selling industrial firmware.", ["Vendor PGP public key signature block on darknet marketplace"]),
        ("Crawl Tor extortion blog to determine countdown timer for corporate data release.", ["Extortion countdown timer and data size metadata extracted from leak post"]),
        ("Search dark web for unredacted government defense contracting bids.", ["Dark-web leak portal document cache matching classified contract numbers"]),
        ("Verify status of dark-web onion relay suspected of nation-state C2 activity.", ["Hidden service consensus status and introduction point descriptors"]),
        ("Extract Jabber negotiation handle from LockBit affiliate disclosure page.", ["Dark-web contact handle and XMPP address regex match"]),
        ("Discover Tor hidden service operated by LockBit ransomware syndicate.", ["Authenticated onion address for LockBit ransomware leak site"]),
        ("Search dark-web forums for 0-day exploit broker auctions.", ["Darknet forum auction post with PGP-verified seller reputation score"]),
        ("Crawl darknet whistleblower portal to verify submission public key.", ["Whistleblower portal HTML payload and submission encryption key"]),
        ("Extract Bitcoin cash-out addresses from ransomware negotiation chat portal.", ["Bitcoin address string parsed from authenticated onion negotiation session"]),
        ("Search onion search engines for stolen law enforcement CAD records.", ["Dark-web search index hit referencing law enforcement computer dispatch logs"]),
        ("Crawl darknet paste site to discover dumped corporate API tokens.", ["Dark-web pastebin snippet containing exposed API private keys"]),
        ("Discover onion service backup mirror for Dread forum following DDoS attack.", ["Verified secondary onion mirror address announced by Dread administration"]),
        ("Extract Tox ID used by ransomware threat actor for private triage.", ["Hexadecimal Tox ID extracted from dark-web extortion victim notice page"]),
        ("Search dark web for proprietary source code repositories of commercial bank.", ["Breach blog listing and source code directory tree on Tor service"]),
        ("Verify whether historical darknet forum was seized by Operation Onymous.", ["Historical darknet seizure notice timestamp and archive mirror"]),
        ("Crawl Tor data broker site to catalog stolen passport scan packages.", ["Identity document package manifest extracted from onion broker page"]),
        ("Search dark-web marketplaces for access broker listings targeting VPNs.", ["Initial access broker listing specifying enterprise SSL VPN credentials"]),
        ("Discover onion site hosting stolen intellectual property from chip foundry.", ["Semiconductor design schematic disclosure on darknet leak site"]),
        ("Extract Monero extortion address from targeted enterprise ransomware note.", ["Monero stealth address extracted from dark-web payment portal"]),
        ("Crawl darknet cyber-mercenary portfolio to list advertised services.", ["Service catalog and pricing sheet extracted from onion mercenary portfolio"]),
        ("Search dark-web leak portals for proprietary insurance actuarial models.", ["Insurance policy database leak listing on darknet extortion blog"]),
        ("Verify if onion service supports Tor v3 next-generation cryptography.", ["Hidden service descriptor confirming 56-character ed25519 public key format"]),
        ("Extract SimpleX chat address from anonymous darknet activist group.", ["SimpleX invite URI parsed from dark-web activist landing page"]),
        ("Search dark web for exfiltrated SCADA engineering diagrams.", ["Industrial control system schematic archive on darknet leak portal"]),
        ("Crawl Tor escrow platform to enumerate active dispute resolution cases.", ["Escrow dispute thread metadata extracted from darknet trading engine"]),
    ]

    for i, (q, ev) in enumerate(pos_specs, 1):
        tasks.append(OnionRoutingTask(
            task_id=f"route_pos_onion_{i:02d}",
            query=q,
            evidence_requirements=ev,
            expected_capabilities_evaluator_only=["onion_intelligence"],
            is_onion_positive=True,
        ))

    # =========================================================================
    # NEGATIVE TASKS (50 Tasks: Corporate, Infra, Identity, Sanctions, General)
    # =========================================================================
    neg_specs = [
        # Corporate Registry
        ("Retrieve certificate of incorporation and registered agent for Apex Technologies in Delaware.", ["Delaware Division of Corporations entity status certificate"], ["corporate_registry_intelligence"]),
        ("Find active company directors and filing history for British engineering firm at Companies House.", ["UK Companies House director registry and micro-entity accounts"], ["corporate_registry_intelligence"]),
        ("Look up registered capital and legal representative for Shanghai manufacturing LLC.", ["National Enterprise Credit Information Publicity System registration"], ["corporate_registry_intelligence"]),
        ("Identify corporate officers and registered office for Dublin holding entity.", ["Companies Registration Office (CRO) Ireland annual return filing"], ["corporate_registry_intelligence"]),
        ("Verify beneficial ownership registry filings for Luxembourg SARL.", ["Luxembourg Business Registers (LBR) extract and share capital ledger"], ["corporate_registry_intelligence"]),
        ("Check statutory director disqualification registry for former European corporate executive.", ["National insolvency and director disqualification register"], ["corporate_registry_intelligence"]),
        ("Determine corporate standing and branch registrations for Tokyo trading company.", ["National Tax Agency corporate number publication and registry extract"], ["corporate_registry_intelligence"]),
        ("Verify registered office and historical name changes for Singapore private limited company.", ["Accounting and Corporate Regulatory Authority (ACRA) business profile"], ["corporate_registry_intelligence"]),
        ("Retrieve commercial register extract for German GmbH from Handelsregister.", ["Gemeinsames Registerportal der Länder commercial register excerpt"], ["corporate_registry_intelligence"]),
        ("Identify shareholder percentage ownership in Zurich private investment AG.", ["Swiss cantonal commercial registry extract and share register"], ["corporate_registry_intelligence"]),

        # Infrastructure / DNS / BGP
        ("Enumerate DNS authoritative nameservers and mail exchangers for apextech.com.", ["Authoritative DNS NS and MX record answers from root servers"], ["infrastructure_discovery"]),
        ("Lookup BGP autonomous system number and IP prefix announcements for AS12389.", ["RIPE / BGP routing table dump and prefix origin validation"], ["infrastructure_discovery"]),
        ("Inspect TLS certificate transparency logs and SAN entries for cloudflare.com.", ["Certificate Transparency log entry and X.509 subject alternative names"], ["infrastructure_discovery"]),
        ("Identify reverse DNS PTR record and upstream transit providers for 198.51.100.1.", ["Reverse DNS PTR query response and WHOIS IP allocation block"], ["infrastructure_discovery"]),
        ("Check whether mail server IP is listed on Spamhaus ZEN composite blocklist.", ["DNSBL lookup response and blocklist policy explanation"], ["infrastructure_discovery"]),
        ("Analyze NTP server stratum and clock jitter for pool.ntp.org cluster.", ["NTP packet response headers and clock synchronization telemetry"], ["infrastructure_discovery"]),
        ("Determine registrant WHOIS contact and registrar lock status for domain example.org.", ["ICANN RDAP / WHOIS directory query response"], ["infrastructure_discovery"]),
        ("Inspect IPv6 prefix delegation and router advertisements for campus network.", ["IPv6 neighbor discovery and router advertisement packet captures"], ["infrastructure_discovery"]),
        ("Identify CDN edge server locations and Anycast POPs for fastly.net.", ["Traceroute round-trip times and geographic latency triangulation"], ["infrastructure_discovery"]),
        ("Verify SPF, DKIM, and DMARC TXT DNS policy records for bank domain.", ["DNS TXT resource record responses containing v=spf1 and v=DMARC1"], ["infrastructure_discovery"]),

        # Identity / People
        ("Find official LinkedIn professional profile and job history for cybersecurity executive.", ["Verified professional social media profile and employment timeline"], ["identity_resolution"]),
        ("Locate academic publications and ORCID researcher identifier for computer scientist.", ["ORCID author profile and indexed peer-reviewed journal papers"], ["identity_resolution"]),
        ("Verify author email address and GPG signature on clearnet Linux kernel mailing list.", ["Public LKML email headers and pgp.mit.edu keyserver confirmation"], ["identity_resolution"]),
        ("Determine speaker biography and presentation schedule for RSA Conference.", ["Conference agenda and speaker profile published on official conference site"], ["identity_resolution"]),
        ("Find public GitHub profile and open-source contributions for developer 'octocat'.", ["GitHub user API profile and public repository commit history"], ["identity_resolution"]),
        ("Verify corporate executive email format pattern using clearnet company press releases.", ["Published press contact emails and MX delivery verification"], ["identity_resolution"]),
        ("Locate patent inventorship filings for semiconductor engineer at USPTO.", ["USPTO Patent Full-Text and Image Database inventor listing"], ["identity_resolution"]),
        ("Find official press interview transcripts for university chancellor.", ["Accredited news organization interview audio and text transcripts"], ["identity_resolution"]),
        ("Verify professional medical license standing with state medical licensing board.", ["State medical board online license verification registry"], ["identity_resolution"]),
        ("Look up bar association admission status for commercial litigation attorney.", ["State bar association directory web page and admission status"], ["general_web_research"]),

        # Sanctions / PEP / Offshore
        ("Screen maritime shipping firm against OFAC Specially Designated Nationals list.", ["OFAC SDN designated entity list and executive order reference"], ["sanctions_and_beneficial_ownership"]),
        ("Check HM Treasury asset freeze consolidated list for Russian financial institution.", ["UK OFSI consolidated sanctions schedule entry"], ["sanctions_and_beneficial_ownership"]),
        ("Determine ultimate beneficial owner of private BVI offshore trust from Panama Papers.", ["Offshore registry beneficial ownership disclosure or ICIJ leak database"], ["sanctions_and_beneficial_ownership"]),
        ("Identify whether deputy energy minister qualifies as Politically Exposed Person.", ["Official national gazette decree and PEP regulatory register"], ["sanctions_and_beneficial_ownership"]),
        ("Screen crude oil tanker IMO number for G7 maritime price cap violation ban.", ["Maritime enforcement authority shadow fleet designation list"], ["sanctions_and_beneficial_ownership"]),
        ("Verify EU restrictive measures designation for defense electronics manufacturer.", ["EU Council Regulation restrictive measures annex gazette"], ["sanctions_and_beneficial_ownership"]),
        ("Check State Secretariat for Economic Affairs SECO sanctions database for Swiss asset freeze.", ["SECO sanctions database entry and decree text"], ["sanctions_and_beneficial_ownership"]),
        ("Assess 50 percent rule aggregate blocked ownership across corporate subsidiaries.", ["Subsidiary corporate share register indicating aggregate blocked ownership"], ["sanctions_and_beneficial_ownership"]),
        ("Determine historical delisting date for European investment vehicle from SDN list.", ["OFAC SDN historical removal notice and Federal Register publication"], ["sanctions_and_beneficial_ownership"]),
        ("Check whether transport firm appears on Japanese METI Foreign End-User List.", ["Japan METI Foreign End User List export control schedule"], ["sanctions_and_beneficial_ownership"]),

        # Keyword Decoys (Contain words like "Tor", "onion", "dark", but are NOT onion intelligence tasks)
        ("Analyze soil nitrogen requirements for Vidalia sweet onion cultivation in Georgia.", ["Agricultural extension bulletin on allium cepa crop management"], ["general_web_research"]),
        ("Explain cellular autophagy regulation mediated by mammalian target of rapamycin (mTOR).", ["Peer-reviewed molecular biology review on mTOR complex 1 kinase"], ["general_web_research"]),
        ("Study cryptographic cell size in Tor onion routing protocol specification (Dingledine 2004).", ["IEEE conference paper PDF document on cryptographic cell size design"], ["general_web_research"]),
        ("Summarize New York Times news reporting on international dark web market takedowns.", ["Archived New York Times newspaper articles and investigative reporting"], ["general_web_research"]),
        ("Review quarterly revenue and cloud security ARR for Darktrace PLC on London Stock Exchange.", ["LSE regulatory news service earnings release and annual report"], ["corporate_registry_intelligence"]),
        ("Explain the origin of the term 'onion skinning' in traditional cel animation techniques.", ["Animation history textbook chapter on cel layering and registration"], ["general_web_research"]),
        ("Inspect culinary recipes for French onion soup with caramelized Gruyere croutons.", ["Published culinary recipe database and ingredient proportions"], ["general_web_research"]),
        ("Read astronomical survey data on the Dark Energy Spectroscopic Instrument (DESI).", ["Astrophysical Journal publication on cosmological redshift data"], ["general_web_research"]),
        ("Look up patent details for Tor-browser hardware acceleration at European Patent Office.", ["EPO Espacenet patent specification and claims sheet"], ["general_web_research"]),
        ("Analyze historical trading volumes for Dark Matter token on decentralized Uniswap pools.", ["DEX on-chain automated market maker liquidity pool event logs"], ["general_web_research"]),
    ]

    for i, (q, ev, exp_caps) in enumerate(neg_specs, 1):
        tasks.append(OnionRoutingTask(
            task_id=f"route_neg_onion_{i:02d}",
            query=q,
            evidence_requirements=ev,
            expected_capabilities_evaluator_only=exp_caps,
            is_onion_positive=False,
        ))

    return tasks
