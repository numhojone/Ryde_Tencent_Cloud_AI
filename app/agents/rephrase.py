"""Rephrase agent: tidies what a human support agent types before it is used or sent.

Two purposes:
- "qa":    the human's question to the case-QA agent. Spelling and grammar fixed, meaning unchanged.
- "rider": a message that goes to the rider. Same clean-up, then a short polite wrapper, in the
           rider's language (English, or Chinese when the rider wrote in Chinese).

Deterministic path (no API key): trim, fix common typos from a small dictionary, capitalise, end with
the right punctuation, and wrap rider messages in a fixed polite template. Offline it cannot translate:
a Chinese rider gets the Chinese template around the English question.
LLM path: only called when the deterministic clean-up changed something (the text was not clean) or a
translation is needed, to save the free-tier quota. The model's answer is checked and the deterministic
result is used if it is empty or implausibly long.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from app.agents.base import BaseAgent

# Common typos and chat shorthand. Keys are lower-case whole words.
TYPOS: dict[str, str] = {
    "teh": "the", "hte": "the", "th": "the", "taht": "that", "tht": "that", "wat": "what", "wht": "what", "waht": "what",
    "wen": "when", "whn": "when", "wher": "where", "wich": "which", "whcih": "which", "becuase": "because", "becasue": "because",
    "bcos": "because", "bc": "because", "cuz": "because", "u": "you", "ur": "your", "pls": "please",
    "plz": "please", "thx": "thanks", "abt": "about", "b4": "before", "ard": "around", "msg": "message", "msgs": "messages",
    "pic": "photo", "pics": "photos", "yday": "yesterday", "tmr": "tomorrow", "dont": "don't", "didnt": "didn't",
    "doesnt": "doesn't", "wasnt": "wasn't", "werent": "weren't", "isnt": "isn't", "cant": "can't", "wont": "won't",
    "couldnt": "couldn't", "im": "I'm", "ive": "I've", "i": "I", "recieve": "receive", "recieved": "received",
    "adress": "address", "definately": "definitely", "seperate": "separate", "occured": "occurred", "untill": "until",
    "drvier": "driver", "drivr": "driver", "dirver": "driver", "drv": "driver", "ridr": "rider", "rdier": "rider",
    "luggae": "luggage", "lugage": "luggage", "luggag": "luggage", "baggae": "baggage", "pasenger": "passenger",
    "passanger": "passenger", "pikcup": "pickup", "picup": "pickup", "lobbby": "lobby",
    "mesage": "message", "messsage": "message", "phne": "phone", "fone": "phone", "minuts": "minutes", "mins": "minutes",
    "min": "minutes", "awnser": "answer", "anwser": "answer", "refnd": "refund", "refud": "refund", "chrage": "charge",
    "chareg": "charge", "chargd": "charged", "arived": "arrived", "arrivd": "arrived", "waitied": "waited",
    "wated": "waited", "wiat": "wait", "calld": "called", "caled": "called", "traffc": "traffic", "trafic": "traffic",
    "acident": "accident", "accidnet": "accident", "speding": "speeding", "photoes": "photos", "evidance": "evidence",
    "shld": "should", "wud": "would", "cud": "could", "confim": "confirm", "confrim": "confirm", "realy": "really", "alot": "a lot", "becaus": "because",
}
_QWORDS = ("what", "when", "where", "which", "who", "whom", "whose", "why", "how", "did", "do", "does", "was", "were",
           "is", "are", "can", "could", "would", "will", "should", "has", "have", "had", "may", "might")


def fix_text(text: str) -> str:
    """Trim, collapse spaces, fix dictionary typos, capitalise, end with ? or . as the sentence needs."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return ""
    if re.search(r"[㐀-鿿]", t):                       # Chinese: only trim and end with full-width punctuation
        return t if re.search(r"[。？！?.!]$", t) else t + ("？" if re.search(r"(吗|呢|么|吧)$|多少|几|哪|谁|什么|是否|有没有|是不是|为什么|怎么", t) else "。")

    def sub(m: re.Match) -> str:
        w = m.group(0)
        rep = TYPOS.get(w.lower())
        if len(w) == 1 and not w.islower():       # "R" in "R-4521" is an id, not shorthand
            rep = "I" if w == "I" else None
        if rep is None:
            return w
        return rep if (rep == "I" or rep.startswith("I'")) else (rep if w.islower() else rep[:1].upper() + rep[1:])

    t = re.sub(r"[A-Za-z0-9']+", sub, t)
    t = re.sub(r"\s+([,.?!;:])", r"\1", t)              # no space before punctuation
    t = re.sub(r"([,;:])(?=[A-Za-z])", r"\1 ", t)       # one space after it
    t = re.sub(r"([?!.])\1+", r"\1", t)                 # "??" -> "?"
    t = t[:1].upper() + t[1:]
    first = re.match(r"[A-Za-z']+", t)
    is_q = t.endswith("?") or bool(first and first.group(0).lower() in _QWORDS)
    t = t.rstrip(" .,;:!?")
    return t + ("?" if is_q else ".")


def to_second_person(text: str) -> str:
    """A question about "the rider" becomes a question to the rider."""
    t = re.sub(r"\b[Tt]he (?:rider|passenger|customer)'s\b", "your", text)
    t = re.sub(r"\b([Ww]as|[Ii]s) (?:the )?(?:rider|passenger|customer)\b",
               lambda m: ("W" if m.group(1)[0] == "W" else "w") + "ere you" if m.group(1).lower() == "was"
               else ("A" if m.group(1)[0] == "I" else "a") + "re you", t)
    t = re.sub(r"\b[Tt]he (?:rider|passenger|customer) (was|is)\b", lambda m: "you " + ("were" if m.group(1) == "was" else "are"), t)
    t = re.sub(r"\b(?:[Tt]he )?(?:rider|passenger|customer)\b", "you", t)
    t = t.replace("乘客", "您")
    return t[:1].upper() + t[1:]


def rider_wrap(clean: str, rider_lang: str) -> str:
    """The polite template for a message to the rider (deterministic)."""
    clean = to_second_person(clean)
    if rider_lang == "zh":
        return f"您好，这里是 Ryde 客服。为了处理您的案件，想请您确认一个问题：{clean}"
    return f"Hello, this is Ryde Support. To help us review your case, could you please answer one question: {clean}"


def rider_note(clean: str, rider_lang: str) -> str:
    """A decision note to the rider (deterministic): no question template, just a courteous lead-in."""
    if rider_lang == "zh":
        return f"Ryde 客服备注：{clean}"
    return f"A note from Ryde Support: {clean}"


def is_clean(text: str) -> bool:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return bool(t) and fix_text(t) == t


class RephraseOut(BaseModel):
    text: str


class RephraseAgent(BaseAgent):
    """Corrects spelling and grammar and sets a professional tone, without changing the meaning."""

    role = "rephrase"
    name = "rephrase"
    parse_schema = RephraseOut

    def __init__(self, emit, mode=None, lang="en", purpose="qa", rider_lang="en"):
        super().__init__(emit, mode=mode, lang=lang)
        self.purpose, self.rider_lang = purpose, rider_lang

    def deterministic(self, text: str) -> str:
        clean = fix_text(text)
        if self.purpose == "rider":
            return rider_wrap(clean, self.rider_lang)
        if self.purpose == "note":
            return rider_note(clean, self.rider_lang)
        return clean

    def needs_model(self, text: str) -> bool:
        """Skip the model when the text is already clean and no translation is needed."""
        translate = self.purpose in ("rider", "note") and self.rider_lang == "zh" and not re.search(r"[㐀-鿿]", text or "")
        return translate or not is_clean(text)

    def tool_schemas(self) -> list[dict]:
        return []

    def system_prompt(self) -> str:
        target = "Simplified Chinese" if self.purpose in ("rider", "note") and self.rider_lang == "zh" else "English"
        job = {"qa": "Fix spelling and grammar of a support agent's question. Keep it a question with the same meaning.",
               "rider": "Rewrite a support agent's question to a ride-hailing customer: polite, professional, short. "
                        "Start with a greeting from Ryde Support.",
               "note": "Rewrite a support agent's note to a ride-hailing customer: polite, professional, short."}[self.purpose]
        return (f"{job} Never add facts, promises or amounts that are not in the text. Write in {target}. "
                'Output strict JSON only: {"text":"..."}')

    def build_user_message(self, context: dict) -> str:
        return context["text"]

    def build_final(self, context: dict, gathered: dict) -> dict:
        return {"text": self.deterministic(context["text"])}

    def _fill_defaults(self, data: dict, context: dict) -> dict:
        return data


async def rephrase(text: str, *, purpose: str = "qa", mode: str | None = None, lang: str = "en",
                   rider_lang: str = "en") -> dict:
    """{original, rephrased, changed, used_model}. Falls back to the deterministic result on any model problem."""
    async def _noop(_ev):
        return None
    agent = RephraseAgent(_noop, mode=mode, lang=lang, purpose=purpose, rider_lang=rider_lang)
    det = agent.deterministic(text)
    used_model = False
    out = det
    if agent._mode() == "llm" and agent.needs_model(text):
        res = await agent.run({"text": text})
        cand = getattr(res.output, "text", None) if res.output is not None else None
        if isinstance(cand, str) and cand.strip() and len(cand) <= 3 * len(text) + 160 and not cand.startswith("[LLM"):
            out, used_model = cand.strip(), True
    original = re.sub(r"\s+", " ", (text or "").strip())
    return {"original": original, "rephrased": out, "changed": out != original, "used_model": used_model}
