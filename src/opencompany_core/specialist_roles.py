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
