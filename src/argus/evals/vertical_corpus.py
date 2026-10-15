"""Frozen Vertical Identity Corpus and Platform Simulation Registry.

Supplies frozen platform databases and web documents for evaluating
cross-platform identity correlation without external network flakiness.
"""

from typing import Any
from argus.crawler.models import Document, generate_unit_id, ContentUnit

# 1. Blackbird Platform Database Simulation (WhatsMyName platform probe data)
VERTICAL_PLATFORM_REGISTRY: dict[str, dict[str, Any]] = {
    "github": {
        "name": "GitHub",
        "cat": "coding",
        "url_template": "https://github.com/{username}",
        "e_string": "profile_loaded",
        "e_code": 200,
        "users": {
            "s0md3v": {
                "url": "https://github.com/s0md3v",
                "display_name": "Somdev Sangwan",
                "bio": "Security Researcher & Developer. Creator of Photon and XSStrike.",
                "location": "India",
            },
            "alex_chen": {
                "url": "https://github.com/alex_chen",
                "display_name": "Alex Chen",
                "bio": "Software Engineer in San Francisco, CA. Building distributed systems.",
                "location": "San Francisco, CA",
            },
            "techlead-marcus": {
                "url": "https://github.com/techlead-marcus",
                "display_name": "Marcus Vance",
                "bio": "Cloud infrastructure architect and open-source contributor.",
                "location": "Seattle, WA",
            },
            "quiet_researcher_88": {
                "url": "https://github.com/quiet_researcher_88",
                "display_name": "",
                "bio": "",
                "location": "",
            },
            "sarah_connor_ai": {
                "url": "https://github.com/sarah_connor_ai",
                "display_name": "Sarah Connor",
                "bio": "Certified Personal Fitness Trainer and bodybuilding coach in Miami, Florida.",
                "location": "Miami, FL",
            },
            "dr_elena_rostova": {
                "url": "https://github.com/dr_elena_rostova",
                "display_name": "Dr. Elena Rostova",
                "bio": "Robotics Perception Lead at AutoSens Perception. Autonomous navigation research.",
                "location": "Boston, MA",
            },
        },
    },
    "twitter": {
        "name": "Twitter",
        "cat": "social",
        "url_template": "https://twitter.com/{username}",
        "e_string": "profile_loaded",
        "e_code": 200,
        "users": {
            "s0md3v": {
                "url": "https://twitter.com/s0md3v",
                "display_name": "Somdev Sangwan",
                "bio": "Security research & open source tools @s0md3v",
                "location": "India",
            },
            "techlead_marcus": {
                "url": "https://twitter.com/techlead_marcus",
                "display_name": "Marcus Vance",
                "bio": "Chief Cloud Architect. Microservices, Kubernetes, and enterprise systems.",
                "location": "Seattle, WA",
            },
            "sarah_connor_ai": {
                "url": "https://twitter.com/sarah_connor_ai",
                "display_name": "Dr. Sarah Connor",
                "bio": "AI Safety Researcher at Cambridge, UK. Aligning foundation models.",
                "location": "Cambridge, UK",
            },
        },
    },
    "medium": {
        "name": "Medium",
        "cat": "blog",
        "url_template": "https://medium.com/@{username}",
        "e_string": "profile_loaded",
        "e_code": 200,
        "users": {
            "s0md3v": {
                "url": "https://medium.com/@s0md3v",
                "display_name": "Somdev Sangwan",
                "bio": "Articles on web application security, OSINT, and automation.",
                "location": "India",
            },
        },
    },
    "devto": {
        "name": "Dev.to",
        "cat": "coding",
        "url_template": "https://dev.to/{username}",
        "e_string": "profile_loaded",
        "e_code": 200,
        "users": {
            "alex_chen": {
                "url": "https://dev.to/alex_chen",
                "display_name": "Alex Chen",
                "bio": "Full-stack developer from SF. React, Python, Distributed Systems.",
                "location": "San Francisco, CA",
            },
        },
    },
    "soundcloud": {
        "name": "Soundcloud",
        "cat": "music",
        "url_template": "https://soundcloud.com/{username}",
        "e_string": "profile_loaded",
        "e_code": 200,
        "users": {
            "alex_chen": {
                "url": "https://soundcloud.com/alex_chen",
                "display_name": "Alex Chen (DJ)",
                "bio": "DJ and electronic music producer based in Berlin, Germany. Techno/House tracks.",
                "location": "Berlin, Germany",
            },
        },
    },
    "pinterest": {
        "name": "Pinterest",
        "cat": "social",
        "url_template": "https://pinterest.com/{username}",
        "e_string": "profile_loaded",
        "e_code": 200,
        "users": {
            "alex_chen": {
                "url": "https://pinterest.com/alex_chen",
                "display_name": "Alex Chen Design",
                "bio": "Interior designer in Austin, TX. Scandinavian minimalist home decor pins.",
                "location": "Austin, TX",
            },
        },
    },
    "linkedin": {
        "name": "LinkedIn",
        "cat": "professional",
        "url_template": "https://linkedin.com/in/{username}",
        "e_string": "profile_loaded",
        "e_code": 200,
        "users": {
            "jbobnar": {
                "url": "https://linkedin.com/in/jbobnar",
                "display_name": "Joe Bobnar",
                "bio": "Plant Manager at Kentucky Truck Plant, Ford Motor Company. Louisville, KY.",
                "location": "Louisville, KY",
            },
        },
    },
    "twitch": {
        "name": "Twitch",
        "cat": "streaming",
        "url_template": "https://twitch.tv/{username}",
        "e_string": "profile_loaded",
        "e_code": 200,
        "users": {
            "jbobnar": {
                "url": "https://twitch.tv/jbobnar",
                "display_name": "J_Bobnar_Gamer",
                "bio": "Competitive Fortnite and Call of Duty streamer in Vancouver, Canada.",
                "location": "Vancouver, Canada",
            },
        },
    },
    "instagram": {
        "name": "Instagram",
        "cat": "social",
        "url_template": "https://instagram.com/{username}",
        "e_string": "profile_loaded",
        "e_code": 200,
        "users": {
            "s0md3v": {
                "url": "https://instagram.com/s0md3v",
                "display_name": "Somdev Sangwan",
                "bio": "Security researcher & developer. Creator of Photon.",
                "location": "India",
                "is_private": False,
            },
            "private_target_user": {
                "url": "https://instagram.com/private_target_user",
                "display_name": "Target Individual (Private Profile)",
                "bio": "Personal account. Follow to request access.",
                "location": "London, UK",
                "is_private": True,
            },
            "alex_chen": {
                "url": "https://instagram.com/alex_chen",
                "display_name": "Alex Chen",
                "bio": "SF Bay Area photographer and coder.",
                "location": "San Francisco, CA",
                "is_private": False,
            },
            "sarah_connor_ai": {
                "url": "https://instagram.com/sarah_connor_ai",
                "display_name": "Sarah Connor Fitness",
                "bio": "Miami personal fitness trainer and lifestyle coach.",
                "location": "Miami, FL",
                "is_private": False,
            },
        },
    },
}

# 2. Frozen Web Documents for Argus Search Engine
def build_vertical_identity_documents() -> list[Document]:
    """Build mock searchable web pages for the vertical identity tasks."""
    docs = []
    
    # Doc 1: s0md3v Developer Profile Article
    d1 = Document(
        document_id="doc_vert_s0md3v",
        url="https://github.com/s0md3v",
        title="Somdev Sangwan (s0md3v) - GitHub",
        text_content=(
            "Somdev Sangwan (@s0md3v) is an open-source cybersecurity researcher and developer. "
            "He is the creator of OSINT tools including Photon, XSStrike, and Breacher. "
            "His active social profiles include twitter.com/s0md3v and medium.com/@s0md3v."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d1)

    # Doc 2: Alex Chen Software Engineer in SF
    d2 = Document(
        document_id="doc_vert_alex_chen_sf",
        url="https://github.com/alex_chen",
        title="Alex Chen (alex_chen) - GitHub",
        text_content=(
            "Alex Chen is a Software Engineer based in San Francisco, CA. "
            "Specializes in distributed systems, backend architectures, and Python/Rust. "
            "Also publishes technical tutorials on dev.to/alex_chen."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d2)

    # Doc 3: Alex Chen DJ in Berlin
    d3 = Document(
        document_id="doc_vert_alex_chen_dj",
        url="https://soundcloud.com/alex_chen",
        title="Alex Chen (alex_chen) - Soundcloud",
        text_content=(
            "Alex Chen is an electronic music producer and resident DJ at Berlin nightlife clubs. "
            "Produces dark progressive techno and deep house. Has no affiliation with computer science."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d3)

    # Doc 4: Joe Bobnar Ford Plant Manager
    d4 = Document(
        document_id="doc_vert_jbobnar",
        url="https://linkedin.com/in/jbobnar",
        title="Joe Bobnar - Plant Manager - Kentucky Truck Plant - Ford Motor Company",
        text_content=(
            "Joe Bobnar serves as Plant Manager at Kentucky Truck Plant in Louisville, Kentucky. "
            "Directs operations and production for Ford F-Series Super Duty trucks, Expedition, and Navigator."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d4)

    # Doc 5: Marcus Vance Cloud Architect
    d5 = Document(
        document_id="doc_vert_techlead_marcus",
        url="https://twitter.com/techlead_marcus",
        title="Marcus Vance (@techlead_marcus) - Twitter",
        text_content=(
            "Marcus Vance (@techlead_marcus) is a Chief Cloud Architect based in Seattle, WA. "
            "Open source projects maintained under github.com/techlead-marcus focusing on Kubernetes."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d5)

    # Doc 6: Dr. Sarah Connor AI Safety
    d6 = Document(
        document_id="doc_vert_sarah_connor_uk",
        url="https://twitter.com/sarah_connor_ai",
        title="Dr. Sarah Connor (@sarah_connor_ai) - Twitter",
        text_content=(
            "Dr. Sarah Connor (@sarah_connor_ai) is a Principal AI Safety Researcher at Cambridge, UK. "
            "Focuses on formal verification and alignment of large foundation models."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d6)

    # Doc 7: Sarah Connor Gym Trainer in Miami
    d7 = Document(
        document_id="doc_vert_sarah_connor_miami",
        url="https://github.com/sarah_connor_ai",
        title="Sarah Connor (sarah_connor_ai) - GitHub",
        text_content=(
            "Sarah Connor is a certified personal fitness trainer in Miami, Florida. "
            "Shares workout routines and nutritional spreadsheets. Unrelated to artificial intelligence."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d7)

    # Doc 8: Dr. Elena Rostova Robotics Lead
    d8 = Document(
        document_id="doc_vert_elena_rostova",
        url="https://github.com/dr_elena_rostova",
        title="Dr. Elena Rostova - GitHub",
        text_content=(
            "Dr. Elena Rostova is the Robotics Perception Lead at AutoSens Perception. "
            "Leads camera vision and lidar perception sensor fusion for autonomous commercial vehicles."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d8)

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
