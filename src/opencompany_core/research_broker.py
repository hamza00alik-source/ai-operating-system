"""Bounded, read-only API Anything research for specialist execution."""
from __future__ import annotations

import json
import re
from uuid import uuid4
from dataclasses import dataclass

from .api_anything import ApiAnythingClient
from .domain import WorkItem
from .model_gateway import ModelGateway, ModelRequest
from .organization import default_organization
from .workforce import RoleSpec


class ResearchBrokerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ResearchOutcome:
    site: str | None
    operation: str | None
    result: dict | None
    reason: str


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _site_ids(discovery: dict) -> tuple[str, ...]:
    found = []
    for item in _walk(discovery):
        candidate = item.get("site")
        if isinstance(candidate, str) and re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", candidate):
            if candidate not in found:
                found.append(candidate)
    return tuple(found[:3])


def _read_operations(catalog: dict, site: str) -> tuple[dict, ...]:
    found = []
    for item in _walk(catalog):
        name = item.get("name") or item.get("op")
        if (
            isinstance(name, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", name)
            and item.get("readOnly") is True
            and item.get("minTier", 99) == 1
        ):
            found.append({
                "site": site, "op": name,
                "summary": str(item.get("summary", ""))[:500],
                "params": item.get("params", item.get("args", {})),
            })
    unique = {}
    for item in found:
        unique[item["op"]] = item
    return tuple(unique.values())[:40]


def _contains_sensitive_args(value) -> bool:
    forbidden_keys = {"password", "token", "secret", "authorization", "api_key", "email", "phone", "customer_id"}
    if isinstance(value, dict):
        return any(
            str(key).casefold() in forbidden_keys or _contains_sensitive_args(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_args(child) for child in value)
    if isinstance(value, str):
        return bool(
            re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", value, re.I)
            or re.search(r"(?<!\d)(?:\+?\d[\d .()-]{8,}\d)(?!\d)", value)
            or re.search(r"\b(?:bearer|authorization|api[_-]?key|secret|password)\b", value, re.I)
            or re.search(r"\b[A-Za-z0-9_-]{32,}\b", value)
        )
    return False


class ResearchBroker:
    """Finds and executes at most one explicitly read-only, plain-HTTP research operation."""

    def __init__(self, client: ApiAnythingClient, gateway: ModelGateway) -> None:
        self.client = client
        self.gateway = gateway

    def collect(self, role: RoleSpec, item: WorkItem) -> ResearchOutcome:
        department_key = next(
            (department.key for department in default_organization().all() if role.key in department.role_keys),
            None,
        )
        if department_key not in {
            "intelligence-research", "product-innovation", "marketing-audience-growth",
            "revenue-partnerships", "customer-operations",
        }:
            return ResearchOutcome(None, None, None, "role is not enabled for external research")
        query = f"{role.title} {item.title}"[:300]
        try:
            discovery = self.client.find_sites(query)
        except Exception as exc:
            return ResearchOutcome(None, None, None, f"research discovery unavailable ({type(exc).__name__})")
        sites = _site_ids(discovery)
        if not sites:
            return ResearchOutcome(None, None, None, "no matching read-only research sites were discovered")
        catalogues = []
        for site in sites:
            try:
                catalogue = self.client.list_operations(site)
            except Exception:
                continue
            operations = _read_operations(catalogue, site)
            if operations:
                catalogues.extend(operations)
        if not catalogues:
            return ResearchOutcome(None, None, None, "no confirmed tier-one read operations were available")
        selection_prompt = (
            "Choose at most one public read-only API Anything operation for the assigned task. "
            "Only select an operation from the exact catalogue below. Do not invent site or op names. "
            "Use only public, non-personal search arguments. Return only JSON with exactly site, op, args. "
            "If no operation is useful, return {\"site\":null,\"op\":null,\"args\":{}}.\n"
            f"Role: {role.title}\nTask title: {item.title}\nTask objective: {item.objective[:2000]}\n"
            f"Allowed tier-one read operations: {json.dumps(catalogues, ensure_ascii=False)}"
        )
        try:
            selection = self.gateway.complete(
                ModelRequest(prompt=selection_prompt, request_id=str(uuid4()), max_output_tokens=700),
                request_budget_usd=0.0, preferred_provider="unorouter",
            )
            chosen = json.loads(selection.text)
        except Exception as exc:
            return ResearchOutcome(None, None, None, f"research selection unavailable ({type(exc).__name__})")
        if not isinstance(chosen, dict) or set(chosen) != {"site", "op", "args"}:
            return ResearchOutcome(None, None, None, "research selector returned an invalid shape")
        if chosen["site"] is None and chosen["op"] is None:
            return ResearchOutcome(None, None, None, "model found no relevant research operation")
        allowed = {(entry["site"], entry["op"]) for entry in catalogues}
        if (chosen["site"], chosen["op"]) not in allowed:
            return ResearchOutcome(None, None, None, "model selected an operation outside the read-only catalogue")
        if not isinstance(chosen["args"], dict) or _contains_sensitive_args(chosen["args"]):
            return ResearchOutcome(None, None, None, "research arguments were invalid or contained sensitive data")
        try:
            result = self.client.call_read(chosen["site"], chosen["op"], chosen["args"], max_age_ms=300000)
        except Exception as exc:
            return ResearchOutcome(chosen["site"], chosen["op"], None, f"read call failed ({type(exc).__name__})")
        if result.get("ok") is not True or result.get("class") != "ok":
            return ResearchOutcome(chosen["site"], chosen["op"], result, "external source returned a non-ok result")
        bounded = json.dumps(result, ensure_ascii=False)[:16000]
        return ResearchOutcome(chosen["site"], chosen["op"], {"bounded_json": bounded}, "read-only research completed")
