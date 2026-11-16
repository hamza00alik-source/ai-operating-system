"""OpenCompany-owned department and role-template catalogue.

These are capability templates, not pre-running agents or imported third-party agents.
"""
from __future__ import annotations

DEPARTMENTS = (
    ("intelligence-research", "Research & Intelligence", "market_intelligence_analyst"),
    ("product-innovation", "Product & R&D", "product_innovation_manager"),
    ("engineering", "Engineering & Technology", "engineering_manager"),
    ("design-creative", "Design & Creative Production", "creative_design_manager"),
    ("marketing-growth", "Marketing & Growth", "growth_marketing_manager"),
    ("sales-marketplace", "Sales & Marketplace Operations", "marketplace_operations_manager"),
    ("customer-operations", "Customer Operations", "customer_operations_manager"),
    ("finance-operations", "Finance & Accounting", "finance_operations_manager"),
    ("legal-compliance", "Legal & Compliance", "legal_compliance_manager"),
    ("quality-workforce", "Quality & Workforce Operations", "quality_workforce_manager"),
)

_MANAGER_TITLES = {
    "intelligence-research": "Market Intelligence Analyst",
    "product-innovation": "Product Innovation Manager",
    "engineering": "Engineering Manager",
    "design-creative": "Creative Design Manager",
    "marketing-growth": "Growth Marketing Manager",
    "sales-marketplace": "Marketplace Operations Manager",
    "customer-operations": "Customer Operations Manager",
    "finance-operations": "Finance Operations Manager",
    "legal-compliance": "Legal & Compliance Manager",
    "quality-workforce": "Quality & Workforce Manager",
}

_SPECIALISTS = {
    "intelligence-research": (
        ("market_demand_researcher", "Market Demand Researcher", ("market", "researcher", "demand")),
        ("competitor_intelligence_analyst", "Competitor Intelligence Analyst", ("competitor", "market", "analysis")),
        ("customer_research_analyst", "Customer Research Analyst", ("customer", "research", "interviews")),
        ("industry_data_analyst", "Industry Data Analyst", ("industry", "data", "analysis")),
        ("research_quality_reviewer", "Research Quality Reviewer", ("research", "quality", "evidence")),
    ),
    "product-innovation": (
        ("product_discovery_researcher", "Product Discovery Researcher", ("product", "research", "discovery")),
        ("product_requirements_analyst", "Product Requirements Analyst", ("product", "requirements", "analysis")),
        ("prototype_planner", "Prototype Planner", ("prototype", "planning", "product")),
        ("product_validation_analyst", "Product Validation Analyst", ("validation", "product", "research")),
        ("roadmap_analyst", "Product Roadmap Analyst", ("roadmap", "planning", "product")),
    ),
    "engineering": (
        ("backend_integration_engineer", "Backend Integration Engineer", ("backend", "api", "integration")),
        ("automation_workflow_engineer", "Automation Workflow Engineer", ("automation", "workflow", "systems")),
        ("platform_reliability_engineer", "Platform Reliability Engineer", ("reliability", "monitoring", "deployment")),
        ("database_systems_engineer", "Database Systems Engineer", ("database", "data", "performance")),
        ("software_quality_engineer", "Software Quality Engineer", ("testing", "quality", "regression")),
    ),
    "design-creative": (
        ("brand_identity_designer", "Brand Identity Designer", ("brand", "identity", "visual")),
        ("product_ui_ux_designer", "Product UI/UX Designer", ("product", "interface", "usability")),
        ("three_d_asset_designer", "3D Asset Designer", ("3d", "modeling", "game assets")),
        ("creative_content_designer", "Creative Content Designer", ("creative", "content", "visual")),
        ("design_systems_specialist", "Design Systems Specialist", ("design system", "components", "consistency")),
    ),
    "marketing-growth": (
        ("search_visibility_specialist", "Search Visibility Specialist", ("seo", "search", "organic growth")),
        ("social_content_strategist", "Social Content Strategist", ("social media", "content", "audience")),
        ("conversion_optimization_analyst", "Conversion Optimization Analyst", ("conversion", "analytics", "experiments")),
        ("growth_campaign_planner", "Growth Campaign Planner", ("campaign", "growth", "planning")),
        ("marketing_performance_analyst", "Marketing Performance Analyst", ("marketing", "performance", "measurement")),
    ),
    "sales-marketplace": (
        ("marketplace_listing_specialist", "Marketplace Listing Specialist", ("marketplace", "listing", "catalogue")),
        ("product_catalogue_analyst", "Product Catalogue Analyst", ("product", "catalogue", "data quality")),
        ("pricing_merchandising_analyst", "Pricing & Merchandising Analyst", ("pricing", "margin", "merchandising")),
        ("order_operations_coordinator", "Order Operations Coordinator", ("orders", "fulfillment", "coordination")),
        ("buyer_enquiry_coordinator", "Buyer Enquiry Coordinator", ("buyer enquiries", "response drafts", "sales support")),
    ),
    "customer-operations": (
        ("customer_support_analyst", "Customer Support Analyst", ("customer support", "issue classification", "resolution")),
        ("order_support_coordinator", "Order Support Coordinator", ("order status", "customer updates", "coordination")),
        ("help_centre_knowledge_editor", "Help Centre Knowledge Editor", ("faq", "documentation", "knowledge base")),
        ("returns_workflow_analyst", "Returns Workflow Analyst", ("returns", "refund policy", "workflow")),
        ("customer_feedback_analyst", "Customer Feedback Analyst", ("feedback", "sentiment", "product insights")),
    ),
    "finance-operations": (
        ("bookkeeping_analyst", "Bookkeeping Analyst", ("bookkeeping", "reconciliation", "records")),
        ("cost_margin_analyst", "Cost & Margin Analyst", ("cost", "margin", "unit economics")),
        ("cashflow_planner", "Cashflow Planner", ("cashflow", "forecast", "liquidity")),
        ("invoice_review_specialist", "Invoice Review Specialist", ("invoice", "expense", "verification")),
        ("financial_controls_analyst", "Financial Controls Analyst", ("controls", "audit", "financial risk")),
    ),
    "legal-compliance": (
        ("intellectual_property_reviewer", "Intellectual Property Reviewer", ("copyright", "licensing", "trademarks")),
        ("marketplace_policy_analyst", "Marketplace Policy Analyst", ("marketplace policy", "platform rules", "compliance")),
        ("privacy_compliance_analyst", "Privacy Compliance Analyst", ("privacy", "data protection", "retention")),
        ("contract_risk_reviewer", "Contract Risk Reviewer", ("contracts", "terms", "risk")),
        ("claims_compliance_reviewer", "Claims Compliance Reviewer", ("claims", "advertising", "substantiation")),
    ),
    "quality-workforce": (
        ("workflow_quality_reviewer", "Workflow Quality Reviewer", ("workflow", "quality", "acceptance criteria")),
        ("role_capability_analyst", "Role Capability Analyst", ("roles", "capabilities", "workforce design")),
        ("agent_evaluation_analyst", "Agent Evaluation Analyst", ("evaluation", "benchmarks", "performance")),
        ("governance_audit_analyst", "Governance Audit Analyst", ("governance", "audit", "approvals")),
        ("workforce_knowledge_coordinator", "Workforce Knowledge Coordinator", ("training", "knowledge", "documentation")),
    ),
}
_GENERIC = (
    ("operations_analyst", "Operations Analyst", ("operations", "analysis")),
    ("workflow_designer", "Workflow Designer", ("workflow", "design")),
    ("documentation_specialist", "Documentation Specialist", ("documentation", "quality")),
    ("risk_reviewer", "Risk Reviewer", ("risk", "review")),
    ("performance_analyst", "Performance Analyst", ("performance", "analysis")),
)

def departments():
    result=[]
    for key,name,manager in DEPARTMENTS:
        role_keys=[manager]
        role_keys.extend(f"{key.replace('-', '_')}_team_{team:02d}_{slot:02d}" for team in range(1,11) for slot in range(1,6))
        result.append({
            "department":key,"name":name,"manager_role_key":manager,"role_keys":role_keys,
            "approval_boundaries":["External publication requires owner approval","Spending and payments require owner approval","Customer commitments require owner approval"],
        })
    return result

def roles():
    result=[]
    for key,name,manager in DEPARTMENTS:
        result.append(_role(manager,_MANAGER_TITLES[key],key,"leadership",("management","planning","review")))
    result.append(_role("chief_executive_orchestrator","Chief Executive Orchestrator","executive","leadership",("executive","orchestration","planning")))
    for department,name,manager in DEPARTMENTS:
        templates=_SPECIALISTS.get(department,_GENERIC)
        for team in range(1,11):
            team_key=f"{department.replace('-', '_')}__team_{team:02d}"
            for slot in range(5):
                if team==1 and department in _SPECIALISTS:
                    role_key,title,caps=templates[slot]
                else:
                    role_key=f"{department.replace('-', '_')}_team_{team:02d}_specialist_{slot+1:02d}"
                    title=f"{name.split('&')[0].strip()} Team {team} Specialist {slot+1}"
                    caps=tuple(set(templates[slot%len(templates)][2]+(department.replace("-"," "),)))
                result.append(_role(role_key,title,department,"specialist",caps,team_key))
    return result

def _role(key,title,department,kind,caps,team_key=None):
    return {
        "role_key":key,"title":title,"department":department,"kind":kind,
        "team_key":team_key or department.replace("-","_")+"__leadership",
        "capabilities":list(caps),
        "prohibited_actions":["spend_money","publish_externally","make_customer_commitments","change_production"],
        "playbook":{"workflow_steps":["Clarify objective and constraints","Gather evidence","Produce a reviewable deliverable","Check quality and risks"],"quality_rubric":["Evidence is traceable","Assumptions are labelled","Risks and limitations are explicit","No prohibited action is taken"]},
    }

ROLE_CATALOGUE=roles()
DEPARTMENT_CATALOGUE=departments()
