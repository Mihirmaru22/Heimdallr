import asyncio
import json
import os
import time
from argus.core.controller import ArgusController
from argus.domain.objective import ResearchObjective
from argus.llm.openrouter import OpenRouterLLMProvider
from argus.search.hybrid import HybridSearchProvider
from argus.search.pipeline import SearchPipeline
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository
from argus.verifier.engine import ExpertVerifier
from argus.worker.engine import WorkerEngine
from argus.brain.planner import ResearchBrain
from argus.brain.system1 import System1DecisionEngine
from argus.contact.resolver import ContactResolutionEngine
from argus.crawler.fetcher import TwoTierFetcher

# Setup environment for OpenRouter Free Models
os.environ["LLM_PROVIDER"] = "openrouter"
os.environ["OPENROUTER_MODEL"] = "nvidia/nemotron-3-super-120b-a12b:free"

TOPICS = [
    {
        "id": "t1_auto_plant",
        "limited": {
            "target": "Dearborn Truck Plant",
            "goal": "Find the exact name of the current Plant Manager of the Dearborn Truck Plant.",
            "fields": ["plant_manager_name"]
        },
        "open": {
            "target": "Ford US Automotive Manufacturing Plants",
            "goal": "Identify management leadership and key details about Ford's US plants, specifically Dearborn.",
            "fields": ["plant_manager", "location", "vehicles_produced"]
        }
    },
    {
        "id": "t2_teamcenter",
        "limited": {
            "target": "Lockheed Martin Siemens Teamcenter",
            "goal": "Does Lockheed Martin use Siemens Teamcenter PLM? Find proof.",
            "fields": ["uses_teamcenter"]
        },
        "open": {
            "target": "Aerospace Companies using Siemens Teamcenter",
            "goal": "Find major aerospace companies that use Siemens Teamcenter software.",
            "fields": ["company_name", "plm_software"]
        }
    },
    {
        "id": "t3_openai_ceo",
        "limited": {
            "target": "OpenAI Current CEO",
            "goal": "Find the exact name of the current CEO of OpenAI.",
            "fields": ["ceo_name"]
        },
        "open": {
            "target": "OpenAI Executive Leadership",
            "goal": "Find the current C-level executives of OpenAI.",
            "fields": ["executive_name", "executive_title"]
        }
    },
    {
        "id": "t4_anthropic_funding",
        "limited": {
            "target": "Anthropic Latest Funding Round Series",
            "goal": "What was the total dollar amount of Anthropic's most recent funding round?",
            "fields": ["latest_funding_amount"]
        },
        "open": {
            "target": "Anthropic Financials and Funding",
            "goal": "Find details on Anthropic's funding history and major investors.",
            "fields": ["funding_round", "amount_raised", "investors"]
        }
    },
    {
        "id": "t5_tesla_texas",
        "limited": {
            "target": "Tesla Giga Texas Plant Manager",
            "goal": "Find the name of the director or plant manager of Tesla Giga Texas.",
            "fields": ["plant_manager"]
        },
        "open": {
            "target": "Tesla Gigafactory Texas Operations",
            "goal": "Find operational details, production capacity, and leadership of Giga Texas.",
            "fields": ["production_capacity", "leadership_names", "location"]
        }
    }
]

async def run_evaluation():
    results = []
    # Disable VCR for live run to hit actual search engines
    os.environ["ARGUS_VCR_MODE"] = "bypass"
    
    for topic in TOPICS:
        print(f"\n{'='*50}")
        print(f"Evaluating Topic: {topic['id']}")
        
        for scope_type in ["limited", "open"]:
            print(f"\n--- Scope: {scope_type.upper()} ---")
            config = topic[scope_type]
            
            # Use unique DB per run to isolate state
            db_path = f"eval_{topic['id']}_{scope_type}.db"
            if os.path.exists(db_path):
                os.remove(db_path)
                
            objective = ResearchObjective(
                target=config["target"],
                target_type="concept",
                intelligence_goal=config["goal"],
                required_fields=config["fields"],
                success_criteria=f"Found {config['fields']}",
                max_tasks=2,
                max_depth=1
            )
            
            db = DatabaseManager(db_path)
            repo = ArgusRepository(db)
            
            llm_provider = OpenRouterLLMProvider(
                model=os.environ["OPENROUTER_MODEL"],
                timeout=120.0,
            )
            
            search_provider = HybridSearchProvider(ddg_max_concurrent=2, timeout=15.0)
            search_pipeline = SearchPipeline(provider=search_provider)
            
            fetcher = TwoTierFetcher()
            worker = WorkerEngine(repo=repo, llm=llm_provider)
            verifier = ExpertVerifier(repo=repo, llm=llm_provider)
            brain = ResearchBrain(repo=repo, llm=llm_provider)
            system1 = System1DecisionEngine()
            contact_resolver = ContactResolutionEngine()
            
            controller = ArgusController(
                repo=repo,
                search_pipeline=search_pipeline,
                fetcher=fetcher,
                worker=worker,
                verifier=verifier,
                brain=brain,
                system1=system1,
                contact_resolver=contact_resolver,
            )
            
            start_time = time.time()
            try:
                # Limit execution to 2 tasks max
                await controller.run(objective, max_crawl_pages_per_task=2)
                success = True
            except Exception as e:
                print(f"Error during execution: {e}")
                success = False
            duration = time.time() - start_time
            
            # Measure yield directly from SQLite WAL ledger
            repo = controller.repo
            claims = repo.list_claims(objective_id=objective.objective_id)
            entities = repo.list_entities(objective_id=objective.objective_id)
            
            res = {
                "topic": topic["id"],
                "scope": scope_type,
                "duration_sec": round(duration, 2),
                "claims_extracted": len(claims),
                "entities_extracted": len(entities),
                "success": success
            }
            results.append(res)
            print(f"Result -> {res}")
            
    with open("round_4_eval_results.json", "w") as f:
        json.dump(results, f, indent=2)
        
    print("\nEVALUATION COMPLETE. Results saved to round_4_eval_results.json")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
