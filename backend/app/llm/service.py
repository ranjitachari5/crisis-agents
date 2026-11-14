"""Bounded Groq usage: natural-language explanations only.

The LLM never allocates, validates, commits or decides trust. It receives a
JSON fact sheet and must explain it. If no key is configured or the call
fails, a deterministic template produces the explanation instead.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.config import Settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the explanation module of CRISIS AGENTS, a multi-agent disaster resource negotiation system. "
    "You do NOT make decisions. Explain the decisions described in the JSON facts for an emergency commander. "
    "Use only numbers present in the facts; never invent values. Be concise and concrete (<= 120 words), "
    "plain text, no markdown headings."
)


class LLMService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.groq_model
        self._client = None
        self.last_error: str | None = None
        if settings.llm_configured:
            try:
                from groq import AsyncGroq
                self._client = AsyncGroq(api_key=settings.groq_api_key, timeout=settings.llm_timeout_s,
                                         max_retries=1)
            except Exception as exc:  # pragma: no cover
                self.last_error = str(exc)
                log.warning("Groq client unavailable: %s", exc)

    @property
    def available(self) -> bool:
        return self._client is not None

    def status(self) -> dict:
        return {"provider": "groq", "model": self.model, "configured": self.settings.llm_configured,
                "available": self.available, "last_error": self.last_error}

    async def complete(self, prompt: str, max_tokens: int = 600) -> str | None:
        if not self._client:
            return None
        try:
            kwargs: dict[str, Any] = dict(model=self.model, max_tokens=max_tokens, temperature=0.2,
                                          messages=[{"role": "system", "content": SYSTEM_PROMPT},
                                                    {"role": "user", "content": prompt}])
            if "gpt-oss" in self.model:
                kwargs["reasoning_effort"] = "low"
            resp = await asyncio.wait_for(self._client.chat.completions.create(**kwargs),
                                          timeout=self.settings.llm_timeout_s + 2)
            text = (resp.choices[0].message.content or "").strip()
            self.last_error = None
            return text or None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            log.warning("Groq call failed, using deterministic fallback: %s", self.last_error)
            return None

    async def explain(self, facts: dict, question: str | None = None) -> dict:
        prompt = (f"Commander question: {question or 'Why is the current allocation what it is?'}\n"
                  f"Facts (JSON):\n{json.dumps(facts, default=str)[:6000]}")
        text = await self.complete(prompt)
        if text:
            return {"text": text, "source": f"groq:{self.model}", "advisory_only": True}
        return {"text": deterministic_explanation(facts), "source": "deterministic_template", "advisory_only": True}

    async def summarize_agreement(self, facts: dict) -> dict:
        prompt = ("Summarise in 2-3 sentences why this allocation was agreed, who conceded what, and any "
                  f"safety implications.\nFacts (JSON):\n{json.dumps(facts, default=str)[:5000]}")
        text = await self.complete(prompt, max_tokens=400)
        if text:
            return {"text": text, "source": f"groq:{self.model}"}
        return {"text": deterministic_agreement_summary(facts), "source": "deterministic_template"}


def deterministic_explanation(f: dict) -> str:
    ag = f.get("agreement")
    if not ag:
        return "No allocation has been committed yet. Start the simulation to run the first negotiation."
    parts = [f"Allocation v{ag['version']} was committed via {ag['method']} with fairness weight "
             f"{f.get('fairness', 0):.2f} (0 = priority, 1 = equity)."]
    parts.append(f"Verified supply is {f.get('verified_supply_mw') or 0:.1f} MW plus up to "
                 f"{f.get('battery_capability_mw') or 0:.1f} MW battery discharge.")
    shortfalls = []
    for aid, a in (f.get("agents") or {}).items():
        alloc, dem, mn = a.get("allocation_mw") or 0, a.get("demand_mw") or 0, a.get("min_safe_mw") or 0
        if alloc < mn - 0.01:
            shortfalls.append(f"{aid} is {mn - alloc:.1f} MW below its safe minimum")
        elif alloc < dem - 0.5:
            parts.append(f"{aid} receives {alloc:.1f} of {dem:.1f} MW requested (minimum {mn:.1f}).")
    if ag.get("degradation_mode"):
        parts.append("Emergency degradation mode is active because safe minimums exceed verified supply: "
                     + "; ".join(shortfalls) + ".")
    neg = f.get("last_negotiation")
    if neg:
        parts.append(f"The last negotiation took {neg.get('rounds')} round(s); converged={neg.get('converged')}, "
                     f"fallback used={neg.get('fallback_used')}.")
    if f.get("cascades"):
        parts.append("Active cascades: " + " | ".join(" → ".join(c["path"]) for c in f["cascades"][:2]))
    return " ".join(parts)


def deterministic_agreement_summary(f: dict) -> str:
    alloc = f.get("allocation", {})
    demands = f.get("demands", {})
    cuts = [f"{k.split('_')[0]} −{demands[k] - v:.1f} MW" for k, v in alloc.items()
            if k in demands and demands[k] - v > 0.5]
    return (f"v{f.get('version')} ({f.get('method')}): "
            + (("concessions " + ", ".join(cuts)) if cuts else "all requests met")
            + (". Degradation mode: unavoidable shortages reported." if f.get("degradation_mode") else "."))
