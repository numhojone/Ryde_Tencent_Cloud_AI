"""Tiny i18n helper: every human-readable string the backend emits exists in English and Chinese.

`lang` is "en" (default) or "zh". Machine fields (ruling enums, clause IDs, tool names) are never translated.
"""
from __future__ import annotations

CUR = "S$"  # display currency (Singapore dollar)


def norm_lang(lang: str | None) -> str:
    l = (lang or "").strip().lower()
    return "zh" if l.startswith("zh") or l in ("cn", "chinese", "中文") else "en"


def L(lang: str, en: str, zh: str) -> str:
    return zh if lang == "zh" else en


def lang_rule(lang: str) -> str:
    """Instruction appended to every LLM system prompt."""
    if lang == "zh":
        return ("\n\n[Output language] Write every human-readable text field (claim, reasoning, evidence_cited, "
                "escalation_summary, classification_reasoning, normalized_claim) in Simplified Chinese. "
                "Keep JSON keys, enum values (upheld/rejected/partial/escalated), clause IDs (CN-1, RD-2 ...), "
                "tool names and numbers unchanged. The rider's complaint may be written in any language; "
                "read it in whatever language it is in.")
    return ("\n\n[Output language] Write every human-readable text field (claim, reasoning, evidence_cited, "
            "escalation_summary, classification_reasoning, normalized_claim) in English, even if the rider's "
            "complaint is in another language or in Singlish, Malay, Tamil or Chinese. Keep JSON keys, enum values, "
            "clause IDs and numbers unchanged. Read the complaint in whatever language it is written in.")
