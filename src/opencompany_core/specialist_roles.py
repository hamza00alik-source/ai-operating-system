"""Curated original specialist role names for OpenCompany's ten departments.

This catalogue is an OpenCompany capability map, not an imported agent roster.
Each department has five specialist teams with five distinct role scopes.
"""
SPECIALIST_TITLES = {
    "executive-office": (
        "Strategy Analyst", "Operating Model Designer", "Portfolio Planning Analyst", "Priority Coordination Specialist", "Decision Brief Writer",
        "Cross-Department Program Manager", "Dependency Resolution Analyst", "Performance Reporting Analyst", "Executive Research Analyst", "Strategic Risk Coordinator",
        "Objective Decomposition Specialist", "Capacity Planning Analyst", "Initiative Tracking Specialist", "Policy Coordination Analyst", "Owner Escalation Analyst",
        "Business Continuity Planner", "Management Information Analyst", "Scenario Planning Analyst", "Governance Documentation Specialist", "Execution Readiness Reviewer",
        "Organizational Design Analyst", "Strategic Communications Drafter", "KPI Framework Analyst", "Resource Allocation Analyst", "Executive Quality Reviewer",
    ),
    "intelligence-research": (
        "Market Demand Researcher", "Competitor Intelligence Analyst", "Buyer Insights Researcher", "Market Sizing Analyst", "Research Verification Specialist",
        "Search Trends Analyst", "Marketplace Demand Analyst", "Pricing Intelligence Researcher", "Category Research Specialist", "Product Review Analyst",
        "Customer Voice Analyst", "Industry Structure Researcher", "Geographic Market Analyst", "Channel Intelligence Analyst", "Supplier Landscape Researcher",
        "Regulatory Landscape Researcher", "Technology Scouting Analyst", "Opportunity Screening Analyst", "Evidence Synthesis Researcher", "Source Reliability Auditor",
        "Trend Forecasting Analyst", "Commercial Benchmark Analyst", "Audience Segmentation Researcher", "Research Data Curator", "Research Methods Reviewer",
    ),
    "product-innovation": (
        "Product Discovery Researcher", "Customer Problem Analyst", "Product Requirements Specialist", "Feature Prioritization Analyst", "Product Validation Planner",
        "User Journey Analyst", "Product Concept Designer", "Prototype Planning Specialist", "Product Specification Writer", "Acceptance Criteria Analyst",
        "Product Experiment Designer", "Usability Research Analyst", "Product Packaging Strategist", "Digital Product Architect", "Product Differentiation Analyst",
        "Product Roadmap Analyst", "Feature Feasibility Analyst", "Product Quality Planner", "Product Documentation Specialist", "Release Readiness Analyst",
        "Product Lifecycle Analyst", "Innovation Scouting Researcher", "Product Analytics Planner", "Customer Value Analyst", "Product Portfolio Reviewer",
    ),
    "engineering-ai-systems": (
        "Backend Software Engineer", "Frontend Software Engineer", "API Integration Engineer", "Database Systems Engineer", "Application Architect",
        "AI Agent Runtime Engineer", "Model Gateway Engineer", "Prompt Systems Engineer", "Agent Memory Engineer", "Multi-Agent Coordination Engineer",
        "Automation Workflow Engineer", "Queue and Scheduling Engineer", "Infrastructure Engineer", "Deployment Systems Engineer", "Observability Engineer",
        "Application Security Engineer", "Identity and Access Engineer", "Privacy Engineering Analyst", "Performance Optimization Engineer", "Reliability Engineer",
        "Test Automation Engineer", "Software Quality Engineer", "Code Review Specialist", "Developer Experience Engineer", "Technical Documentation Engineer",
    ),
    "media-creative-production": (
        "Creative Director Analyst", "Video Concept Developer", "Scriptwriter", "Storyboard Artist", "Creative Researcher",
        "Image Generation Specialist", "Video Generation Specialist", "3D Asset Concept Artist", "3D Model Production Planner", "Motion Design Specialist",
        "Video Editing Specialist", "Audio Postproduction Specialist", "Caption and Subtitle Specialist", "Thumbnail Designer", "Visual Brand Designer",
        "Content Repurposing Producer", "Short-Form Video Producer", "Long-Form Video Producer", "Animation Production Planner", "Scene Composition Artist",
        "Creative Asset Librarian", "Media Rights Researcher", "Visual Quality Reviewer", "Production Workflow Coordinator", "Creative Performance Analyst",
    ),
    "marketing-audience-growth": (
        "Audience Research Analyst", "Content Strategy Specialist", "SEO Research Specialist", "Keyword Mapping Analyst", "Editorial Calendar Planner",
        "Social Channel Strategist", "Short-Form Content Strategist", "Long-Form Content Strategist", "Community Insights Analyst", "Organic Growth Analyst",
        "Conversion Funnel Analyst", "Landing Page Copywriter", "Email Content Drafter", "Brand Messaging Specialist", "Content Distribution Planner",
        "Search Visibility Analyst", "Content Refresh Specialist", "Audience Retention Analyst", "Creator Partnership Researcher", "Campaign Measurement Analyst",
        "Content Quality Editor", "Marketing Experiment Designer", "Referral Growth Analyst", "Affiliate Content Researcher", "Marketing Compliance Reviewer",
    ),
    "revenue-partnerships": (
        "Marketplace Category Analyst", "Product Listing Researcher", "Listing Copywriter", "Marketplace SEO Specialist", "Marketplace Pricing Analyst",
        "Competitor Offer Analyst", "Product Margin Analyst", "Sales Opportunity Researcher", "Partnership Research Analyst", "Supplier Qualification Analyst",
        "Commercial Proposal Drafter", "Sales Enablement Writer", "Offer Positioning Analyst", "Revenue Forecast Analyst", "Marketplace Policy Analyst",
        "Conversion Optimization Analyst", "Catalog Operations Specialist", "Product Data Quality Analyst", "Order Economics Analyst", "Channel Expansion Analyst",
        "Affiliate Program Analyst", "B2B Inquiry Qualification Analyst", "Commercial Risk Analyst", "Listing Quality Reviewer", "Revenue Performance Analyst",
    ),
    "customer-operations": (
        "Customer Feedback Analyst", "Support Triage Specialist", "Customer Knowledge Writer", "Help Center Content Specialist", "Customer Journey Analyst",
        "Service Quality Analyst", "Customer Onboarding Planner", "Customer Education Writer", "Issue Root Cause Analyst", "Escalation Coordinator",
        "Order Workflow Analyst", "Fulfilment Process Analyst", "Delivery Status Researcher", "Returns Process Analyst", "Service Level Analyst",
        "Customer Sentiment Analyst", "Support Response Drafter", "Customer Data Quality Analyst", "Service Automation Analyst", "Customer Retention Analyst",
        "Operational Documentation Specialist", "Customer Experience Tester", "Complaint Pattern Analyst", "Service Recovery Planner", "Customer Operations Reviewer",
    ),
    "finance-risk": (
        "Cost Accounting Analyst", "Unit Economics Analyst", "Budget Planning Analyst", "Cash Flow Modelling Analyst", "Revenue Reconciliation Analyst",
        "Provider Cost Auditor", "API Usage Cost Analyst", "Infrastructure Cost Analyst", "Pricing and Margin Analyst", "Financial Forecast Analyst",
        "Payment Process Risk Analyst", "Fraud Pattern Researcher", "Commercial Risk Analyst", "Operational Risk Analyst", "Privacy Risk Analyst",
        "Security Risk Analyst", "Licensing Risk Analyst", "Regulatory Research Analyst", "Business Continuity Risk Analyst", "Internal Control Analyst",
        "Audit Evidence Coordinator", "Financial Data Quality Analyst", "Cost Anomaly Investigator", "Scenario Modelling Analyst", "Risk Reporting Reviewer",
    ),
    "organizational-learning-quality": (
        "Agent Performance Evaluator", "Agent Capability Analyst", "Task Outcome Evaluator", "Model Quality Evaluator", "Prompt Quality Reviewer",
        "Research Evidence Auditor", "Factual Accuracy Reviewer", "Output Consistency Reviewer", "Software Test Auditor", "Security Review Analyst",
        "Process Improvement Analyst", "Incident Learning Coordinator", "Root Cause Investigator", "Knowledge Base Curator", "Training Data Quality Analyst",
        "Evaluation Dataset Designer", "Benchmark Design Analyst", "Regression Analysis Specialist", "Improvement Proposal Analyst", "Change Impact Reviewer",
        "Autonomy Boundary Auditor", "Approval Compliance Auditor", "Operational Maturity Analyst", "Cross-Team Quality Coordinator", "Independent Release Reviewer",
    ),
}


# Second independently curated wave: each department gains five additional
# capability teams, bringing the specialist workforce to fifty per department.
EXTRA_SPECIALIST_TITLES = {
    "executive-office": (
        "Strategic Portfolio Analyst", "Business Model Analyst", "Operating Cadence Designer", "Decision Rights Analyst", "Executive Metrics Engineer",
        "Cross-Functional Delivery Analyst", "Strategic Initiative Controller", "Organizational Capacity Researcher", "Executive Knowledge Manager", "Governance Process Analyst",
        "Scenario Stress Tester", "Strategic Dependency Mapper", "Enterprise Planning Analyst", "Management Review Facilitator", "Policy Impact Analyst",
        "Transformation Planning Specialist", "Benefits Realization Analyst", "Internal Communications Planner", "Board Report Analyst", "Strategic Assumptions Auditor",
        "Priority Conflict Mediator", "Operating Risk Analyst", "Executive Workflow Designer", "Strategic Roadmap Controller", "Decision Follow-Through Analyst",
    ),
    "intelligence-research": (
        "Consumer Behaviour Researcher", "Search Intent Analyst", "Competitor Pricing Tracker", "Marketplace Review Miner", "Demand Signal Analyst",
        "Product Category Mapper", "Customer Interview Synthesizer", "Public Data Researcher", "Market Entry Analyst", "Industry News Monitor",
        "Supplier Capability Researcher", "Channel Economics Analyst", "Geospatial Demand Analyst", "Buyer Objection Researcher", "Purchase Intent Analyst",
        "Research Citation Auditor", "Survey Methodology Analyst", "Trend Signal Classifier", "Market Saturation Analyst", "Competitor Feature Tracker",
        "Commercial Data Analyst", "Research Automation Designer", "Evidence Gap Analyst", "Forecast Accuracy Reviewer", "Opportunity Due Diligence Analyst",
    ),
    "product-innovation": (
        "Product Strategy Researcher", "Jobs To Be Done Analyst", "Product Opportunity Mapper", "Value Proposition Designer", "Feature Economics Analyst",
        "Product Workflow Architect", "Digital Download Product Designer", "Game Utility Product Planner", "Product Bundle Designer", "Prototype Test Analyst",
        "Product Accessibility Reviewer", "Product Localization Planner", "Product Onboarding Designer", "Product Supportability Analyst", "Product Differentiation Researcher",
        "Product Pricing Experimenter", "Product Packaging Reviewer", "Product Documentation Architect", "Product Release Coordinator", "Product Feedback Analyst",
        "Product Adoption Analyst", "Product Retention Researcher", "Product Metrics Designer", "Product Roadmap Risk Analyst", "Product Sunset Planner",
    ),
    "engineering-ai-systems": (
        "Python Platform Engineer", "TypeScript Application Engineer", "API Contract Engineer", "Database Reliability Engineer", "SQLite Optimization Engineer",
        "Distributed Systems Analyst", "Agent Evaluation Engineer", "LLM Reliability Engineer", "Inference Routing Engineer", "Context Management Engineer",
        "Retrieval Systems Engineer", "Workflow State Engineer", "Event Processing Engineer", "Background Job Engineer", "Cloud Runtime Engineer",
        "Container Security Engineer", "Secrets Management Engineer", "Session Security Engineer", "Threat Modelling Engineer", "Dependency Security Analyst",
        "Load Testing Engineer", "Chaos Testing Engineer", "Accessibility Test Engineer", "Release Automation Engineer", "Incident Response Engineer",
    ),
    "media-creative-production": (
        "Art Direction Researcher", "Character Design Specialist", "Environment Concept Artist", "Game Prop Concept Artist", "3D Character Sculpting Planner",
        "3D Rigging Workflow Specialist", "3D Materials Artist", "Texture Production Specialist", "Lighting and Rendering Artist", "Game Animation Planner",
        "Visual Effects Planner", "Compositing Specialist", "Sound Design Planner", "Voiceover Script Specialist", "Music Rights Researcher",
        "Video Colour Workflow Specialist", "Motion Graphics Designer", "Infographic Designer", "Product Mockup Artist", "Creative Prompt Engineer",
        "Asset Export Specialist", "Media Format Quality Analyst", "Visual Consistency Auditor", "Creative Version Controller", "Media Production Cost Analyst",
    ),
    "marketing-audience-growth": (
        "Audience Persona Researcher", "Search Intent Strategist", "Technical SEO Analyst", "On-Page SEO Specialist", "Content Brief Architect",
        "Editorial Standards Editor", "Content Cluster Planner", "Video SEO Specialist", "Social Listening Analyst", "Community Growth Planner",
        "Audience Funnel Analyst", "Lead Magnet Planner", "Conversion Copy Editor", "Email Lifecycle Strategist", "Organic Distribution Analyst",
        "Content Analytics Engineer", "Retention Experiment Analyst", "Creator Economy Researcher", "Partnership Content Planner", "Affiliate Funnel Analyst",
        "Brand Consistency Auditor", "Marketing Attribution Analyst", "Campaign Experiment Reviewer", "Audience Trust Analyst", "Content Repurposing Strategist",
    ),
    "revenue-partnerships": (
        "Marketplace Policy Researcher", "Marketplace Fee Analyst", "Listing Conversion Analyst", "Product Feed Specialist", "Catalog Taxonomy Analyst",
        "Offer Comparison Analyst", "Competitive Positioning Analyst", "Digital Goods Pricing Analyst", "B2B Market Researcher", "Inbound Lead Researcher",
        "Supplier Onboarding Analyst", "Partner Due Diligence Analyst", "Commercial Terms Analyst", "Proposal Quality Editor", "Sales Process Designer",
        "Revenue Operations Analyst", "Sales Forecast Modeller", "Commission Structure Analyst", "Affiliate Partner Researcher", "Channel Profitability Analyst",
        "Order Conversion Analyst", "Refund Exposure Analyst", "Listing Compliance Auditor", "Commercial Evidence Reviewer", "Revenue Experiment Analyst",
    ),
    "customer-operations": (
        "Customer Intent Classifier", "Support Knowledge Architect", "Help Centre Information Designer", "Customer Onboarding Writer", "Product Tutorial Designer",
        "Support Workflow Analyst", "Service Queue Analyst", "Response Quality Auditor", "Customer Escalation Analyst", "Complaint Resolution Planner",
        "Order Exception Analyst", "Fulfilment Quality Analyst", "Delivery Exception Researcher", "Returns Eligibility Analyst", "Customer Promise Auditor",
        "Customer Privacy Reviewer", "Support Automation Designer", "Customer Feedback Taxonomist", "Customer Churn Analyst", "Customer Success Planner",
        "Service Recovery Analyst", "Customer Journey Measurement Analyst", "Knowledge Freshness Auditor", "Support Capacity Planner", "Operational Handoff Analyst",
    ),
    "finance-risk": (
        "Management Accounting Analyst", "Contribution Margin Analyst", "Cash Conversion Analyst", "Working Capital Analyst", "Revenue Recognition Researcher",
        "Provider Invoice Auditor", "Free Tier Quota Analyst", "Cloud Cost Forecaster", "Pricing Sensitivity Analyst", "Scenario Finance Modeller",
        "Payment Reconciliation Analyst", "Transaction Anomaly Researcher", "Chargeback Risk Analyst", "Vendor Concentration Analyst", "Business Exposure Analyst",
        "Data Protection Risk Analyst", "Access Control Auditor", "Open Source Licence Analyst", "Terms Change Monitor", "Continuity Scenario Analyst",
        "Control Testing Specialist", "Financial Evidence Reviewer", "Cost Forecast Variance Analyst", "Liquidity Risk Analyst", "Enterprise Risk Dashboard Analyst",
    ),
    "organizational-learning-quality": (
        "Agent Task Routing Evaluator", "Specialist Role Coverage Auditor", "Manager Decision Quality Evaluator", "Delegation Outcome Analyst", "Task Acceptance Rubric Designer",
        "Model Response Grounding Auditor", "Citation Completeness Reviewer", "Hallucination Pattern Analyst", "Output Usability Evaluator", "Cross-Run Consistency Analyst",
        "Workflow Bottleneck Analyst", "Operational Experiment Designer", "Incident Trend Analyst", "Knowledge Retrieval Evaluator", "Memory Provenance Auditor",
        "Evaluation Case Curator", "Adversarial Test Designer", "Regression Coverage Analyst", "Change Proposal Evaluator", "Release Risk Assessor",
        "Autonomous Action Boundary Tester", "Owner Approval Trace Auditor", "Agent Availability Analyst", "Interdepartmental Quality Auditor", "Post-Release Outcome Reviewer",
    ),
}

DEPARTMENT_LABELS = {
    "executive-office": "Executive Office",
    "intelligence-research": "Intelligence & Research",
    "product-innovation": "Product & Innovation",
    "engineering-ai-systems": "Engineering & AI Systems",
    "media-creative-production": "Media & Creative Production",
    "marketing-audience-growth": "Marketing & Audience Growth",
    "revenue-partnerships": "Revenue & Partnerships",
    "customer-operations": "Customer Experience & Operations",
    "finance-risk": "Finance & Risk",
    "organizational-learning-quality": "Organizational Learning & Quality",
}
