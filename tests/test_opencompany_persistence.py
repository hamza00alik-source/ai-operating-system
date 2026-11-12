from datetime import datetime, timezone
from uuid import uuid4

from opencompany_core.domain import AgentProfile, AgentState, AuditRecord, TaskState, WorkItem
from opencompany_core.persistence import SQLiteStore


def test_work_item_round_trip(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    dependency = uuid4()
    item = WorkItem(uuid4(), "Prepare launch brief", "Produce a validated launch brief",
                    "product", state=TaskState.READY, depends_on=(dependency,))
    store.save_work_item(item)
    assert store.get_work_item(item.id) == item
    assert store.list_work_items(state=TaskState.READY) == (item,)
    store.close()


def test_agent_profile_round_trip(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    agent = AgentProfile(uuid4(), "Market Analyst", "research",
                         "Assess market evidence", ("market_research",),
                         state=AgentState.ACTIVE, role_key="market_intelligence_analyst",
                         team_key="management")
    store.save_agent(agent)
    assert store.get_agent(agent.id) == agent
    store.close()


def audit_record(action):
    return AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner",
        action=action, subject_type="work_item", subject_id="work-1",
        outcome="recorded", correlation_id="corr-1",
        details={"source": "unit-test"},
    )


def test_audit_chain_accepts_appended_events(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    store.append_audit_record(audit_record("work.created"))
    store.append_audit_record(audit_record("work.reviewed"))
    assert store.audit_event_count() == 2
    assert store.verify_audit_chain()
    store.close()


def test_audit_chain_detects_payload_tampering(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    store.append_audit_record(audit_record("work.created"))
    with store._lock:
        store._connection.execute(
            "UPDATE audit_events SET payload_json='{}' WHERE sequence=1"
        )
    assert not store.verify_audit_chain()
    store.close()


def test_invalid_list_limit_is_rejected(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    try:
        store.list_work_items(limit=0)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "limit" in str(exc)
    store.close()


def test_work_item_and_audit_record_commit_together(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    item = WorkItem(uuid4(), "Review product brief", "Verify product requirements",
                    "quality", state=TaskState.REVIEW)
    event = audit_record("work_item.review")
    store.save_work_item_with_audit(item, event)
    assert store.get_work_item(item.id) == item
    assert store.audit_event_count() == 1
    assert store.verify_audit_chain()
    store.close()


def test_schema_v1_migrates_agent_role_identity_columns(tmp_path):
    import sqlite3

    path = tmp_path / "legacy-v1.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE agent_profiles (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, department TEXT NOT NULL,
            purpose TEXT NOT NULL, capabilities_json TEXT NOT NULL,
            state TEXT NOT NULL, revision INTEGER NOT NULL
        );
        CREATE TABLE work_items (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, objective TEXT NOT NULL,
            department TEXT NOT NULL, state TEXT NOT NULL, assigned_agent_id TEXT,
            dependencies_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE audit_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
            occurred_at TEXT NOT NULL, payload_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE
        );
        PRAGMA user_version = 1;
    """)
    connection.close()

    store = SQLiteStore(path)
    columns = {row["name"] for row in store._connection.execute(
        "PRAGMA table_info(agent_profiles)"
    ).fetchall()}
    version = store._connection.execute("PRAGMA user_version").fetchone()[0]
    assert {"role_key", "team_key"} <= columns
    work_item_columns = {row["name"] for row in store._connection.execute("PRAGMA table_info(work_items)").fetchall()}
    assert "business_id" in work_item_columns
    assert version == 8
    store.close()


def test_work_items_round_trip_and_filter_by_business_unit(tmp_path):
    store = SQLiteStore(tmp_path / "business-scope.sqlite3")
    agency = WorkItem(
        uuid4(), "Agency supplier research", "Research third-party suppliers",
        "intelligence-research", business_id="physical-agency",
    )
    brand = WorkItem(
        uuid4(), "Own-brand product research", "Research own-brand demand",
        "intelligence-research", business_id="physical-brand",
    )
    digital = WorkItem(
        uuid4(), "Digital product research", "Research downloadable products",
        "intelligence-research", business_id="digital-products",
    )
    for item in (agency, brand, digital):
        store.save_work_item(item)
    assert store.get_work_item(agency.id).business_id == "physical-agency"
    assert store.list_work_items(business_id="physical-agency") == (agency,)
    assert store.list_work_items(business_id="physical-brand") == (brand,)
    assert store.list_work_items(business_id="digital-products") == (digital,)
    store.close()


def test_work_item_business_unit_cannot_be_changed_after_creation(tmp_path):
    store = SQLiteStore(tmp_path / "immutable-business-scope.sqlite3")
    item_id = uuid4()
    agency = WorkItem(
        item_id, "Agency task", "Research a supplier", "research",
        business_id="physical-agency",
    )
    store.save_work_item(agency)
    changed = WorkItem(
        item_id, "Agency task", "Research a supplier", "research",
        business_id="physical-brand",
    )
    try:
        store.save_work_item(changed)
    except ValueError as exc:
        assert "immutable" in str(exc)
    else:
        raise AssertionError("business scope must not be mutable after task creation")
    assert store.get_work_item(item_id).business_id == "physical-agency"
    store.close()



def test_commercial_persistence_rejects_provisioning_business_unit(tmp_path):
    from opencompany_core.business_units import BusinessUnitRegistry
    from opencompany_core.venture_portfolio import VenturePortfolio

    store = SQLiteStore(tmp_path / "commercial-business-scope.sqlite3")
    portfolio = VenturePortfolio(store._connection, store._lock)
    registry = BusinessUnitRegistry(store._connection, store._lock)
    opportunity = portfolio.create(
        title="New software venture", slug="new-software-venture",
        business_model="software", description="A scoped software service",
        target_market="International businesses",
    )
    portfolio.transition(opportunity["id"], status="researching", rationale="Research started")
    portfolio.transition(opportunity["id"], status="validated", rationale="Evidence reviewed")
    approved = portfolio.transition(
        opportunity["id"], status="approved_to_launch",
        rationale="Owner approved launch planning", confirm_owner_approval=True,
    )
    unit = registry.provision_from_opportunity(
        portfolio, approved["id"], business_id="new-software-unit",
        name="New Software Unit", unit_type="software", delivery_class="software-access",
        description="Software access only", target_market="International businesses",
        confirm_owner_approval=True,
    )
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": "commercial-opportunity-1", "business_id": unit["business_id"],
        "customer_name": "Example Customer", "customer_need": "Software access",
        "created_at": now, "updated_at": now,
    }
    try:
        store.create_commercial_opportunity(record, audit_record("commercial.opportunity.created"))
    except ValueError as exc:
        assert "not operational" in str(exc)
    else:
        raise AssertionError("provisioning business unit must not create commercial records")
    assert store.get_commercial_opportunity(record["id"]) is None
    store.close()



def test_schema_v7_migrates_commercial_tables_without_losing_rows_or_foreign_keys(tmp_path):
    import sqlite3

    path = tmp_path / "legacy-v7.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE commercial_opportunities (
            id TEXT PRIMARY KEY,
            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand','digital-products')),
            customer_name TEXT NOT NULL, customer_contact TEXT, customer_need TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT 'new' CHECK(stage IN ('new','qualified','proposal','won','lost','on_hold')),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_commercial_opportunities_unit ON commercial_opportunities(business_id, created_at);
        CREATE TABLE commercial_products (
            id TEXT PRIMARY KEY,
            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand','digital-products')),
            name TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','archived')),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_commercial_products_unit ON commercial_products(business_id, status, created_at);
        CREATE TABLE commercial_quotes (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL REFERENCES commercial_opportunities(id),
            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand','digital-products')),
            title TEXT NOT NULL, currency TEXT NOT NULL CHECK(length(currency)=3),
            currency_exponent INTEGER NOT NULL CHECK(currency_exponent BETWEEN 0 AND 3),
            subtotal_minor INTEGER NOT NULL CHECK(subtotal_minor > 0), terms TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved_for_delivery','accepted','rejected','void')),
            acceptance_reference TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_commercial_quotes_scope ON commercial_quotes(business_id, opportunity_id, created_at);
        CREATE TABLE commercial_quote_items (
            id TEXT PRIMARY KEY,
            quote_id TEXT NOT NULL REFERENCES commercial_quotes(id) ON DELETE CASCADE,
            product_id TEXT NOT NULL REFERENCES commercial_products(id),
            description TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price_minor INTEGER NOT NULL CHECK(unit_price_minor > 0),
            line_total_minor INTEGER NOT NULL CHECK(line_total_minor > 0)
        );
        CREATE INDEX idx_commercial_quote_items_quote ON commercial_quote_items(quote_id);
        CREATE TABLE commercial_orders (
            id TEXT PRIMARY KEY, quote_id TEXT NOT NULL UNIQUE REFERENCES commercial_quotes(id),
            opportunity_id TEXT NOT NULL REFERENCES commercial_opportunities(id),
            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand','digital-products')),
            customer_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'awaiting_owner_fulfilment' CHECK(status IN ('awaiting_owner_fulfilment','in_progress','fulfilled','cancelled')),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_commercial_orders_scope ON commercial_orders(business_id, status, created_at);
        CREATE TABLE commercial_suppliers (
            id TEXT PRIMARY KEY,
            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand')),
            relationship_type TEXT NOT NULL CHECK(relationship_type IN ('agency_supplier','own_brand_supplier')),
            name TEXT NOT NULL, contact_name TEXT, email TEXT, phone TEXT, country TEXT,
            product_categories_json TEXT NOT NULL,
            verification_status TEXT NOT NULL DEFAULT 'draft' CHECK(verification_status IN ('draft','verified','blocked')),
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            CHECK((business_id='physical-agency' AND relationship_type='agency_supplier')
               OR (business_id='physical-brand' AND relationship_type='own_brand_supplier'))
        );
        CREATE INDEX idx_commercial_suppliers_scope ON commercial_suppliers(business_id, verification_status, created_at);

        INSERT INTO commercial_opportunities VALUES
            ('opp-1','physical-agency','Buyer A','buyer@example.test','Physical goods','qualified','2026-01-01','2026-01-02');
        INSERT INTO commercial_products VALUES
            ('prod-1','physical-agency','Salt','Product description','food','active','2026-01-01','2026-01-02');
        INSERT INTO commercial_quotes VALUES
            ('quote-1','opp-1','physical-agency','Quote A','USD',2,100,'Terms','draft',NULL,'2026-01-01','2026-01-02');
        INSERT INTO commercial_quote_items VALUES
            ('line-1','quote-1','prod-1','Salt',1,100,100);
        INSERT INTO commercial_orders VALUES
            ('order-1','quote-1','opp-1','physical-agency','Buyer A','awaiting_owner_fulfilment','2026-01-01','2026-01-02');
        INSERT INTO commercial_suppliers VALUES
            ('supplier-1','physical-agency','agency_supplier','Supplier A',NULL,NULL,NULL,'PK','[]','verified','','2026-01-01','2026-01-02');
        PRAGMA user_version = 7;
    """)
    connection.close()

    store = SQLiteStore(path)
    db = store._connection
    assert db.execute("PRAGMA user_version").fetchone()[0] == 8
    assert db.execute("SELECT business_id FROM commercial_opportunities WHERE id='opp-1'").fetchone()[0] == "physical-agency"
    assert db.execute("SELECT id FROM commercial_quote_items WHERE id='line-1'").fetchone()[0] == "line-1"
    assert db.execute("SELECT id FROM commercial_orders WHERE id='order-1'").fetchone()[0] == "order-1"
    assert db.execute("SELECT id FROM commercial_suppliers WHERE id='supplier-1'").fetchone()[0] == "supplier-1"
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert {"idx_commercial_opportunities_unit", "idx_commercial_products_unit",
            "idx_commercial_quotes_scope", "idx_commercial_quote_items_quote",
            "idx_commercial_orders_scope", "idx_commercial_suppliers_scope"} <= {
        row["name"] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    # The schema accepts a new unit identity; application writes still require
    # an operational registry record at the persistence boundary.
    db.execute(
        """INSERT INTO commercial_opportunities
           (id,business_id,customer_name,customer_need,stage,created_at,updated_at)
           VALUES('opp-2','new-software-unit','Buyer B','Software access','new','2026-01-03','2026-01-03')"""
    )
    db.execute(
        """INSERT INTO commercial_suppliers
           (id,business_id,relationship_type,name,product_categories_json,created_at,updated_at)
           VALUES('supplier-2','new-physical-unit','supplier','Supplier B','[]','2026-01-03','2026-01-03')"""
    )
    assert db.execute("SELECT COUNT(*) FROM commercial_opportunities").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM commercial_suppliers").fetchone()[0] == 2
    store.close()
