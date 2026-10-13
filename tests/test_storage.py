import sqlite3

import pytest

from argus.crawler.models import Document
from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.event import EventType, ResearchEvent
from argus.domain.evidence import Evidence
from argus.domain.objective import ResearchObjective
from argus.domain.task import ResearchTask, TaskStatus
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository


@pytest.fixture
def repo() -> ArgusRepository:
    """Provide a fresh in-memory repository for each test."""
    db = DatabaseManager(":memory:")
    return ArgusRepository(db)


def test_objective_crud(repo: ArgusRepository):
    obj = ResearchObjective(
        target="US Automobile Manufacturers",
        target_type="industry",
        intelligence_goal="Identify plants and leaders",
        required_fields=["plants", "leaders", "phone_numbers"],
        success_criteria="At least 5 plants verified",
        max_tasks=25,
        max_depth=2,
    )
    repo.save_objective(obj)

    retrieved = repo.get_objective(obj.objective_id)
    assert retrieved is not None
    assert retrieved.objective_id == obj.objective_id
    assert retrieved.target == "US Automobile Manufacturers"
    assert retrieved.required_fields == ["plants", "leaders", "phone_numbers"]
    assert retrieved.max_tasks == 25
    assert retrieved.max_depth == 2

    # Test non-existent
    assert repo.get_objective("non_existent_id") is None


def test_task_storage_and_upsert(repo: ArgusRepository):
    # Setup parent objective first for FK integrity
    obj = ResearchObjective(
        target="Ford",
        target_type="company",
        intelligence_goal="Find plants",
        required_fields=["plants"],
        success_criteria="Done",
    )
    repo.save_objective(obj)

    task = ResearchTask(
        objective_id=obj.objective_id,
        title="Find Kentucky Truck Plant",
        description="Search web for plant info",
        priority=5,
    )
    repo.save_task(task)

    retrieved = repo.get_task(task.task_id)
    assert retrieved is not None
    assert retrieved.status == TaskStatus.READY
    assert retrieved.priority == 5

    # Update task (UPSERT test)
    task.status = TaskStatus.RUNNING
    repo.save_task(task)

    updated = repo.get_task(task.task_id)
    assert updated is not None
    assert updated.status == TaskStatus.RUNNING

    # Add a second task
    task2 = ResearchTask(
        objective_id=obj.objective_id,
        title="Find Michigan Assembly",
        description="Search web for Michigan plant",
        priority=10,
    )
    repo.save_task(task2)

    # List all tasks for objective
    all_tasks = repo.list_tasks(obj.objective_id)
    assert len(all_tasks) == 2
    # Verify priority ordering (task2 with priority 10 first)
    assert all_tasks[0].task_id == task2.task_id

    # Filter by status
    running_tasks = repo.list_tasks(obj.objective_id, status=TaskStatus.RUNNING)
    assert len(running_tasks) == 1
    assert running_tasks[0].task_id == task.task_id


def test_entity_storage_and_filtering(repo: ArgusRepository):
    entity1 = Entity(
        entity_type="facility",
        canonical_name="Kentucky Truck Plant",
        aliases=["KTP", "Louisville Truck Plant"],
        attributes={"address": "Louisville, KY", "employees": 9000},
    )
    entity2 = Entity(
        entity_type="company",
        canonical_name="Ford Motor Company",
        aliases=["Ford"],
        attributes={"ticker": "F"},
    )
    repo.save_entity(entity1)
    repo.save_entity(entity2)

    retrieved = repo.get_entity(entity1.entity_id)
    assert retrieved is not None
    assert retrieved.canonical_name == "Kentucky Truck Plant"
    assert "KTP" in retrieved.aliases
    assert retrieved.attributes["employees"] == 9000

    # Filter by entity_type
    facilities = repo.list_entities(entity_type="facility")
    assert len(facilities) == 1
    assert facilities[0].canonical_name == "Kentucky Truck Plant"


def test_evidence_storage(repo: ArgusRepository):
    evidence = Evidence(
        source_id="src_doc_100",
        url="https://media.ford.com/plants/ktp",
        passage="Kentucky Truck Plant builds the Super Duty.",
        char_start=45,
        char_end=88,
        confidence=0.99,
    )
    repo.save_evidence(evidence)

    retrieved = repo.get_evidence(evidence.evidence_id)
    assert retrieved is not None
    assert retrieved.url == "https://media.ford.com/plants/ktp"
    assert retrieved.char_start == 45
    assert retrieved.confidence == 0.99


def test_claim_storage_and_filters(repo: ArgusRepository):
    # Create entity first for FK
    entity = Entity(
        entity_type="facility",
        canonical_name="Kentucky Truck Plant",
    )
    repo.save_entity(entity)

    claim1 = Claim(
        subject_entity_id=entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="Jane Smith",
        status=ClaimStatus.SUPPORTED,
        evidence_ids=["evi_01", "evi_02"],
        confidence=0.92,
    )
    claim2 = Claim(
        subject_entity_id=entity.entity_id,
        predicate="LOCATED_AT",
        object_value="Louisville, KY",
        status=ClaimStatus.PENDING,
        evidence_ids=["evi_03"],
        confidence=0.88,
    )
    repo.save_claim(claim1)
    repo.save_claim(claim2)

    retrieved = repo.get_claim(claim1.claim_id)
    assert retrieved is not None
    assert retrieved.predicate == "HAS_PLANT_MANAGER"
    assert retrieved.status == ClaimStatus.SUPPORTED
    assert retrieved.evidence_ids == ["evi_01", "evi_02"]

    # Filter claims by status
    supported_claims = repo.list_claims(status=ClaimStatus.SUPPORTED)
    assert len(supported_claims) == 1
    assert supported_claims[0].claim_id == claim1.claim_id

    # Filter claims by subject
    all_subject_claims = repo.list_claims(subject_entity_id=entity.entity_id)
    assert len(all_subject_claims) == 2


def test_event_audit_trail(repo: ArgusRepository):
    obj = ResearchObjective(
        target="Ford",
        target_type="company",
        intelligence_goal="Find plants",
        required_fields=["plants"],
        success_criteria="Done",
    )
    repo.save_objective(obj)

    e1 = ResearchEvent(
        objective_id=obj.objective_id,
        event_type=EventType.RESEARCH_STARTED,
        payload={"query": "Ford manufacturing plants"},
    )
    e2 = ResearchEvent(
        objective_id=obj.objective_id,
        task_id="tsk_001",
        event_type=EventType.SEARCH_EXECUTED,
        payload={"query": "Ford KTP manager", "result_count": 10},
    )
    repo.record_event(e1)
    repo.record_event(e2)

    events = repo.list_events(obj.objective_id)
    assert len(events) == 2
    assert events[0].event_type == EventType.RESEARCH_STARTED
    assert events[1].event_type == EventType.SEARCH_EXECUTED
    assert events[1].payload["result_count"] == 10

    # Filter events by task_id
    task_events = repo.list_events(obj.objective_id, task_id="tsk_001")
    assert len(task_events) == 1
    assert task_events[0].event_id == e2.event_id


def test_foreign_key_enforcement(repo: ArgusRepository):
    # Attempting to insert a task pointing to a non-existent objective should fail
    orphan_task = ResearchTask(
        objective_id="non_existent_objective",
        title="Orphan Task",
        description="Should fail foreign key",
    )
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_task(orphan_task)


def test_objective_id_scoping_for_entities_and_claims(repo: ArgusRepository):
    obj1 = ResearchObjective(
        target="Target 1",
        target_type="company",
        intelligence_goal="Goal 1",
        required_fields=["field1"],
        success_criteria="Done",
    )
    obj2 = ResearchObjective(
        target="Target 2",
        target_type="company",
        intelligence_goal="Goal 2",
        required_fields=["field2"],
        success_criteria="Done",
    )
    repo.save_objective(obj1)
    repo.save_objective(obj2)

    ent1 = Entity(
        canonical_name="Entity 1",
        entity_type="company",
        objective_id=obj1.objective_id,
    )
    ent2 = Entity(
        canonical_name="Entity 2",
        entity_type="company",
        objective_id=obj2.objective_id,
    )
    repo.save_entity(ent1)
    repo.save_entity(ent2)

    assert len(repo.list_entities(objective_id=obj1.objective_id)) == 1
    assert (
        repo.list_entities(objective_id=obj1.objective_id)[0].canonical_name
        == "Entity 1"
    )
    assert len(repo.list_entities(objective_id=obj2.objective_id)) == 1
    assert (
        repo.list_entities(objective_id=obj2.objective_id)[0].canonical_name
        == "Entity 2"
    )

    c1 = Claim(
        subject_entity_id=ent1.entity_id,
        predicate="FIELD1",
        object_value="Val1",
        status=ClaimStatus.SUPPORTED,
        objective_id=obj1.objective_id,
    )
    c2 = Claim(
        subject_entity_id=ent2.entity_id,
        predicate="FIELD2",
        object_value="Val2",
        status=ClaimStatus.SUPPORTED,
        objective_id=obj2.objective_id,
    )
    repo.save_claim(c1)
    repo.save_claim(c2)

    assert len(repo.list_claims(objective_id=obj1.objective_id)) == 1
    assert repo.list_claims(objective_id=obj1.objective_id)[0].predicate == "FIELD1"
    assert len(repo.list_claims(objective_id=obj2.objective_id)) == 1
    assert repo.list_claims(objective_id=obj2.objective_id)[0].predicate == "FIELD2"


def test_concurrent_transactions_on_single_sqlite_connection():
    """Bug 3.1 Regression Test:

    Verify that concurrent transactions across multiple threads on a single SQLite
    connection are serialized cleanly via threading.RLock without OperationalErrors
    (such as 'cannot start a transaction within a transaction').
    """
    import concurrent.futures

    db = DatabaseManager(":memory:")
    repo = ArgusRepository(db)

    obj = ResearchObjective(
        target="Concurrent Target",
        target_type="company",
        intelligence_goal="Stress test concurrent writes",
        required_fields=["field1"],
        success_criteria="Done",
    )
    repo.save_objective(obj)

    num_records = 40
    entities = [
        Entity(
            canonical_name=f"Entity {i}",
            entity_type="facility",
            objective_id=obj.objective_id,
        )
        for i in range(num_records)
    ]

    def insert_worker(entity: Entity) -> None:
        repo.save_entity(entity)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(insert_worker, ent) for ent in entities]
        for future in concurrent.futures.as_completed(futures):
            # If a concurrency race condition occurs, future.result() will raise sqlite3.OperationalError
            future.result()

    stored = repo.list_entities(objective_id=obj.objective_id)
    assert len(stored) == num_records
    stored_names = {e.canonical_name for e in stored}
    expected_names = {f"Entity {i}" for i in range(num_records)}
    assert stored_names == expected_names


def test_nested_transactions_with_savepoints():
    """Verify that nested transaction contexts use savepoints cleanly and commit all changes."""
    db = DatabaseManager(":memory:")
    repo = ArgusRepository(db)

    obj = ResearchObjective(
        target="Nested Test",
        target_type="company",
        intelligence_goal="Test nested transactions",
        required_fields=["field1"],
        success_criteria="Done",
    )

    with db.transaction():
        repo.save_objective(obj)
        with db.transaction():
            ent = Entity(
                canonical_name="Nested Facility",
                entity_type="facility",
                objective_id=obj.objective_id,
            )
            repo.save_entity(ent)

    assert repo.get_objective(obj.objective_id) is not None
    assert len(repo.list_entities(objective_id=obj.objective_id)) == 1


def test_nested_transaction_rollback_preserves_outer_transaction():
    """Verify that an inner transaction failure rolls back only to its savepoint,

    allowing the outer transaction to handle the exception and proceed.
    """
    db = DatabaseManager(":memory:")
    repo = ArgusRepository(db)

    obj = ResearchObjective(
        target="Savepoint Rollback Test",
        target_type="company",
        intelligence_goal="Test savepoint rollback",
        required_fields=["field1"],
        success_criteria="Done",
    )
    repo.save_objective(obj)

    with db.transaction():
        ent1 = Entity(
            canonical_name="Committed Facility",
            entity_type="facility",
            objective_id=obj.objective_id,
        )
        repo.save_entity(ent1)

        try:
            with db.transaction():
                ent2 = Entity(
                    canonical_name="Failed Facility",
                    entity_type="facility",
                    objective_id=obj.objective_id,
                )
                repo.save_entity(ent2)
                raise ValueError("Deliberate failure inside nested transaction")
        except ValueError:
            pass

        ent3 = Entity(
            canonical_name="Second Committed Facility",
            entity_type="facility",
            objective_id=obj.objective_id,
        )
        repo.save_entity(ent3)

    stored_entities = repo.list_entities(objective_id=obj.objective_id)
    names = {e.canonical_name for e in stored_entities}
    assert "Committed Facility" in names
    assert "Second Committed Facility" in names
    assert "Failed Facility" not in names


def test_document_persistence_idempotent_on_repeated_crawls():
    """Bug 3.2 Regression Test:

    Verify that saving a Document for a previously crawled URL updates the existing row
    and preserves the canonical document_id, rather than inserting duplicate rows.
    """
    db = DatabaseManager(":memory:")
    repo = ArgusRepository(db)

    # First crawl of URL
    doc1 = Document(
        url="https://media.ford.com/plants/ktp",
        title="Ford KTP - Version 1",
        text_content="Initial text content about Kentucky Truck Plant.",
        status_code=200,
        fetch_method="http",
    )
    repo.save_document(doc1)
    original_id = doc1.document_id

    # Repeated crawl of the same URL produces a new Document object with a new random document_id
    doc2 = Document(
        url="https://media.ford.com/plants/ktp",
        title="Ford KTP - Version 2 (Updated)",
        text_content="Updated text content with new plant leadership details.",
        status_code=200,
        fetch_method="http",
    )
    assert doc2.document_id != original_id  # Pre-condition: fresh UUID generated

    repo.save_document(doc2)

    # Idempotency checks:
    # 1. doc2's document_id is synchronized with the existing stored document_id
    assert doc2.document_id == original_id

    # 2. Only 1 row exists in documents table for this URL
    with db.transaction() as cur:
        cur.execute(
            "SELECT COUNT(*) as cnt FROM documents WHERE url = ?;",
            ("https://media.ford.com/plants/ktp",),
        )
        count = cur.fetchone()["cnt"]
        assert count == 1

    # 3. Content is updated to the latest crawl
    retrieved_by_id = repo.get_document(original_id)
    assert retrieved_by_id is not None
    assert retrieved_by_id.title == "Ford KTP - Version 2 (Updated)"
    assert (
        retrieved_by_id.text_content
        == "Updated text content with new plant leadership details."
    )

    # 4. Retrieval by URL works seamlessly
    retrieved_by_url = repo.get_document_by_url("https://media.ford.com/plants/ktp")
    assert retrieved_by_url is not None
    assert retrieved_by_url.document_id == original_id
    assert retrieved_by_url.title == "Ford KTP - Version 2 (Updated)"


def test_autonomous_matrix_materializer_and_purge(repo: ArgusRepository):
    """Test Autonomous Matrix Materializer:

    1. Correct schema with 11 columns.
    2. Zero raw UUIDs — dereferenced to human strings, verified emails/phones.
    3. Handles forward and reverse leadership relationships.
    4. Comprehensive evidence URLs collected across all associated claims.
    5. purge_plant_leadership_matrix cleans table without schema errors.
    """
    obj = ResearchObjective(
        target="US Auto Manufacturers",
        target_type="industry",
        intelligence_goal="Find plants and leadership",
        required_fields=["manufacturing_plant", "plant_head", "tech_lead", "contact_info"],
        success_criteria="Matrix populated",
    )
    repo.save_objective(obj)

    # 1. Plants (Assembly & Propulsion)
    ktp = Entity(
        objective_id=obj.objective_id,
        entity_type="assembly_plant",
        canonical_name="Kentucky Truck Plant",
        attributes={"location": "3001 Chamberlain Ln, Louisville, KY"},
    )
    giga_tx = Entity(
        objective_id=obj.objective_id,
        entity_type="facility",
        canonical_name="Gigafactory Texas",
        attributes={"location": "13101 Harold Green Rd, Austin, TX"},
    )
    repo.save_entity(ktp)
    repo.save_entity(giga_tx)

    # 2. Leaders
    joe = Entity(
        objective_id=obj.objective_id,
        entity_type="person",
        canonical_name="Joe Hinrichs",
        attributes={"email": "joe.hinrichs@ford.com", "phone": "(502) 429-2000"},
    )
    drew = Entity(
        objective_id=obj.objective_id,
        entity_type="person",
        canonical_name="Drew Baglino",
        attributes={"email": "dbaglino@tesla.com"},
    )
    repo.save_entity(joe)
    repo.save_entity(drew)

    # 3. Evidence
    ev1 = Evidence(
        source_id="src1",
        url="https://media.ford.com/content/fordmedia/fna/us/en/news/2023/ktp-update.html",
        passage="Kentucky Truck Plant switchboard and management update.",
        confidence=0.98,
    )
    ev2 = Evidence(
        source_id="src2",
        url="https://ir.tesla.com/press-release/giga-texas-milestone",
        passage="Gigafactory Texas engineering leadership milestone.",
        confidence=0.96,
    )
    repo.save_evidence(ev1)
    repo.save_evidence(ev2)

    # 4. Claims: KTP forward claims
    repo.save_claim(
        Claim(
            objective_id=obj.objective_id,
            subject_entity_id=ktp.entity_id,
            predicate="HAS_PLANT_MANAGER",
            object_value="Joe Hinrichs",
            object_entity_id=joe.entity_id,
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[ev1.evidence_id],
        )
    )
    repo.save_claim(
        Claim(
            objective_id=obj.objective_id,
            subject_entity_id=ktp.entity_id,
            predicate="HAS_FACILITY_PHONE",
            object_value="(502) 429-2000",
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[ev1.evidence_id],
        )
    )

    # 5. Claims: Giga Texas reverse claims (Drew is Chief Engineer of Giga TX)
    repo.save_claim(
        Claim(
            objective_id=obj.objective_id,
            subject_entity_id=drew.entity_id,
            predicate="CHIEF_ENGINEER_OF",
            object_value=giga_tx.canonical_name,
            object_entity_id=giga_tx.entity_id,
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[ev2.evidence_id],
        )
    )
    repo.save_claim(
        Claim(
            objective_id=obj.objective_id,
            subject_entity_id=giga_tx.entity_id,
            predicate="HAS_FACILITY_PHONE",
            object_value="(512) 516-8000",
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[ev2.evidence_id],
        )
    )

    # 6. Materialize
    count = repo.materialize_plant_leadership_matrix(objective_id=obj.objective_id)
    assert count == 2

    with repo.db.transaction() as cur:
        cur.execute("SELECT * FROM plant_leadership_matrix ORDER BY plant_name ASC")
        rows = cur.fetchall()
        assert len(rows) == 2

        # Verify Giga Texas (reverse claim tech lead)
        r0 = rows[0]
        assert r0["plant_name"] == "Gigafactory Texas"
        assert r0["plant_location"] == "13101 Harold Green Rd, Austin, TX"
        assert r0["plant_contact"] == "(512) 516-8000"
        assert r0["tech_head"] == "Drew Baglino"
        assert r0["tech_head_email"] == "dbaglino@tesla.com"
        assert "https://ir.tesla.com/press-release/giga-texas-milestone" in r0["source_urls"]

        # Verify KTP (forward claim plant manager)
        r1 = rows[1]
        assert r1["plant_name"] == "Kentucky Truck Plant"
        assert r1["plant_location"] == "3001 Chamberlain Ln, Louisville, KY"
        assert r1["plant_contact"] == "(502) 429-2000"
        assert r1["plant_head"] == "Joe Hinrichs"
        assert r1["plant_head_email"] == "joe.hinrichs@ford.com"
        assert r1["plant_head_phone"] == "(502) 429-2000"
        assert "https://media.ford.com/content/fordmedia/fna/us/en/news/2023/ktp-update.html" in r1["source_urls"]

    # 7. Test Purge
    repo.purge_plant_leadership_matrix()
    with repo.db.transaction() as cur:
        cur.execute("SELECT COUNT(*) FROM plant_leadership_matrix")
        assert cur.fetchone()[0] == 0

