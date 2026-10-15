"""Rider advocate agent."""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents import cases
from app.models import AdvocateCase


class RiderAdvocate(BaseAgent):
    role = "advocate"
    name = "rider_advocate"
    parse_schema = AdvocateCase
    side = "rider"

    def system_prompt(self) -> str:
        return (
            f"You are the {self.side.upper()} ADVOCATE AGENT of the RydeResolve ride-hailing dispute platform. You represent the {self.side}.\n\n"
            "You work under the Ryde Dispute Resolution Policy v2.1 (sections 1 route deviation, 2 no-show charge, 3 fare dispute, 4 property damage).\n"
            "Duties:\n"
            "1. Call the tools to gather evidence (trip data, GPS, chat, app events, traffic reference, fare breakdown, damage evidence, profiles, "
            "policy, and search_precedents for similar past rulings).\n"
            "2. Build one case: claim, requested_outcome, requested_amount, policy_clauses_referenced (use section numbers such as 1.3), "
            "evidence_cited (specific data points), reasoning.\n\n"
            "Hard rule: never fabricate evidence; cite only data the tools returned. You lean towards your side but stay honest: "
            "if the evidence goes against you, say so and lower the request.\n\n"
            "Output strict JSON (no code fences):\n"
            f'{{"agent":"{self.side}_advocate","side":"{self.side}","claim":"...","requested_outcome":"...",'
            '"requested_amount":0.0,"policy_clauses_referenced":[],"evidence_cited":[],"reasoning":"..."}'
        )

    def build_user_message(self, context: dict) -> str:
        return ("Dispute ticket:\n" + json.dumps(context["ticket"], ensure_ascii=False, indent=2) +
                f"\n\nGather evidence and build the case on the {self.side}'s behalf. Cite only real data returned by the tools.")

    def build_playbook(self, context: dict) -> list[dict]:
        return cases.playbook(self.lang, context["ticket"])

    def build_final(self, context: dict, gathered: dict) -> dict:
        t = context["ticket"]
        f = cases.compute_facts(t["dispute_type"], gathered)
        return cases.advocate_case(self.side, t["dispute_type"], f, gathered, self.lang)
