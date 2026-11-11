"""Deterministic business-line guardrails for task and workflow intake.

These checks are intentionally conservative: they reject explicit cross-line
fulfillment intent, not incidental mentions in research or marketing copy.
"""
from __future__ import annotations

import re

BUSINESS_IDS = {"core", "physical-agency", "physical-brand", "digital-products"}

_DIGITAL_FULFILLMENT = re.compile(
    r"\b(?:deliver|fulfil|fulfill|ship|provide|sell|supply|replace|substitute|complete)\b"
    r".{0,55}\b(?:digital downloads?|downloadable files?|software|apps?|"
    r"game assets?|3d models?|templates?|plugins?|source code|licenses?)\b"
    r"|\b(?:digital downloads?|downloadable files?|software|apps?|game assets?|"
    r"3d models?|templates?|plugins?|source code)\b.{0,55}"
    r"\b(?:order|customer|buyer|client|fulfilment|fulfillment|delivery)\b",
    re.IGNORECASE | re.DOTALL,
)
_PHYSICAL_FULFILLMENT = re.compile(
    r"\b(?:deliver|fulfil|fulfill|ship|manufacture|produce|sell|supply|stock|"
    r"replace|substitute)\b.{0,55}\b(?:physical goods?|products?|items?|"
    r"inventory|hardware|salt|food|garments?|packaging|cargo|shipment)\b"
    r"|\b(?:physical goods?|products?|items?|inventory|hardware|salt|food|"
    r"garments?|packaging|cargo|shipment)\b.{0,55}"
    r"\b(?:order|customer|buyer|client|fulfilment|fulfillment|delivery|shipping)\b",
    re.IGNORECASE | re.DOTALL,
)

def validate_business_task_scope(business_id: str, title: str, description: str = "") -> None:
    """Reject explicit wrong-business fulfillment; unknown scope fails closed."""
    scope = (business_id or "core").strip()
    if scope not in BUSINESS_IDS:
        raise ValueError("Unknown business environment; refusing unscoped work.")
    text = f"{title or ''}\n{description or ''}"[:15000]
    if scope in {"physical-agency", "physical-brand"} and _DIGITAL_FULFILLMENT.search(text):
        raise ValueError(
            "Business-scope conflict: this physical-products business cannot fulfil an order "
            "with a digital product. Create the work under digital-products only if the customer "
            "actually ordered a digital deliverable."
        )
    if scope == "digital-products" and _PHYSICAL_FULFILLMENT.search(text):
        raise ValueError(
            "Business-scope conflict: the digital-products business cannot promise or fulfil "
            "physical goods, manufacturing, inventory or shipping. Route physical orders to the "
            "correct physical-products business."
        )

def validate_workflow_scope(template_id: str, business_id: str) -> None:
    """Keep product-specific workflow templates inside their matching business line."""
    if business_id not in BUSINESS_IDS:
        raise ValueError("Unknown business environment.")
    if template_id == "digital-product-launch" and business_id != "digital-products":
        raise ValueError(
            "The digital-product-launch workflow can only run inside the digital-products business."
        )
