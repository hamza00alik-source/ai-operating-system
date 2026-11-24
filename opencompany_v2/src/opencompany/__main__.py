"""Local smoke-test entry point."""
from opencompany.store import Store
from opencompany.domain import CompanyEvent

def main():
    store=Store()
    store.append_event(CompanyEvent(kind="system_started",actor="system",entity_type="runtime",entity_id="local",details={"version":"0.1.0"}))
    print("OpenCompany core initialized.")
    print("Event chain integrity:", "verified" if store.verify_event_chain() else "FAILED")
    print("Tasks:", len(store.list_tasks()), "| Opportunities:", len(store.list_opportunities()))
    store.close()
if __name__ == "__main__": main()
