"""Story -> structured facts, rule-based (works with no API key).

The rider's story is the only input. Everything returned here must be something the story
actually says: a field the story does not state stays null (or an empty list). Nothing is
filled in from the platform's records; comparing the story with the records is a separate,
informational step (app/trip_match.claim_check).
"""
from __future__ import annotations

import difflib
import re
from functools import lru_cache

from app.i18n import L

# ---------------------------------------------------------------- numbers

_NUM = r"(\d+(?:\.\d{1,2})?)"
_CUR_PRE = r"(?:s\$|sgd\s*|\$|rm\s*|¥|￥|rmb\s*)"
_CUR_POST = r"(?:元|块钱|块|dollars?|bucks|sgd|ringgit)"
_AMOUNT_CUR = re.compile(rf"{_CUR_PRE}\s*{_NUM}|{_NUM}\s*{_CUR_POST}", re.I)
# A bare number with two decimals ("16.50") is money unless a unit or am/pm follows it.
_AMOUNT_DEC = re.compile(r"(?<![\d.$])(\d+\.\d{2})(?!\d|\s*(?:am|pm|km|min|%|分|点))", re.I)
# A bare number right after a money word ("the quote was 12").
_MONEY_WORD = (r"(?:fare|quote|quoted|price|charged?|paid|pay|fee|cost me|billed|"
               r"报价|收了|扣了|付了|车费|费用|caj|bayar|harga|tambang|கட்டணம்)")
_AMOUNT_CUE = re.compile(_MONEY_WORD + r"[^\d.!?。\n]{0,14}?(?<![\d.])(\d+(?:\.\d{1,2})?)(?![\d.]|\s*(?:am|pm|km|min|%|分|点|:))",
                         re.I)
_SPEED = re.compile(r"(\d+(?:\.\d+)?)\s*多?\s*(?:km/h|kmh|kph|km/j|km\s*per\s*hour|kilomet\w*\s*(?:per|an)\s*hour|"
                    r"公里每小时|公里/小时|公里/时|码)", re.I)
_DIST = re.compile(r"(\d+(?:\.\d+)?)\s*多?\s*(?:km|kilomet(?:er|re)s?|公里|கி\.?மீ)", re.I)
_DUR = re.compile(r"(\d+)\s*(?:min(?:ute)?s?|分钟|minit|நிமிட)", re.I)


def _overlaps(span, spans):
    return any(span[0] < b and a < span[1] for a, b in spans)


def extract_numbers(text: str) -> dict:
    """Every number in the story that has a unit we understand: money, speed, distance, duration.

    Returns {"amounts": [{value, start, end}], "speeds": [...], "distances": [...], "durations": [...]}.
    Amounts are in the order they appear.
    """
    text = text or ""
    taken: list[tuple[int, int]] = []
    out: dict[str, list] = {"amounts": [], "speeds": [], "distances": [], "durations": []}

    def add(kind, m, grp=None):
        g = grp if grp is not None else next(i for i in range(1, (m.lastindex or 1) + 1) if m.group(i))
        span = (m.start(), m.end())
        if _overlaps(span, taken):
            return
        try:
            v = float(m.group(g).replace(",", "."))
        except (TypeError, ValueError):
            return
        taken.append(span)
        out[kind].append({"value": v, "start": m.start(g), "end": m.end(g)})

    for m in _SPEED.finditer(text):
        add("speeds", m, 1)
    for m in _DIST.finditer(text):
        add("distances", m, 1)
    for m in _DUR.finditer(text):
        add("durations", m, 1)
    for m in _AMOUNT_CUR.finditer(text):
        add("amounts", m)
    for m in _AMOUNT_DEC.finditer(text):
        add("amounts", m, 1)
    for m in _AMOUNT_CUE.finditer(text):
        s, e = m.start(1), m.end(1)
        if not _overlaps((s, e), taken):
            taken.append((s, e))
            out["amounts"].append({"value": float(m.group(1)), "start": s, "end": e})
    out["amounts"].sort(key=lambda a: a["start"])
    return out


# Words near an amount that say what the amount is.
_ROLE_CUES = {
    "quote": ("upfront quote", "quote", "quoted", "upfront", "estimate", "estimated", "expected", "normally", "usually",
              "usually pay", "normally pay", "usually cost", "usually costs", "normally cost", "normally costs", "always pay",
              "should be", "should cost", "supposed to", "报价", "预估", "预计", "本来", "原本", "平时", "sebut harga",
              "anggaran", "biasanya", "மதிப்பீடு"),
    "charged": ("charged", "charge me", "end up charge", "charge", "end up", "fare was","fare of", "final fare", "final", "paid", "pay", "cost me", "billed",
                "kena", "收了", "收我", "扣了", "扣我", "付了", "最后", "dikenakan", "caj", "bayar", "வசூல்"),
    "difference": ("difference", "extra", "excess", "overcharged by", "差额", "差价", "多收了", "多收", "多付", "多了",
                   "beza", "lebih", "வித்தியாசம்"),
}
_FEE_CUES = {
    "cleaning_fee": ("cleaning fee", "cleaning charge", "clean fee", "清洁费", "清洗费", "yuran pembersihan",
                     "caj pembersihan", "சுத்தம்"),
    "cancellation_fee": ("cancellation fee", "cancel fee", "cancellation charge", "no-show fee", "no show fee",
                         "取消费", "爽约费", "caj pembatalan", "yuran pembatalan", "ரத்து கட்டணம்"),
    "damage_fee": ("damage fee", "repair fee", "repair cost", "damage charge", "损坏费", "维修费", "yuran kerosakan"),
}
_SENT_END = re.compile(r"[.!?。！？;；\n](?=\s|$)|[。！？；\n]")


def _clause_window(text: str, start: int, end: int, back: int = 70, fwd: int = 26) -> tuple[str, str]:
    """Text before/after an amount, cut at the sentence boundary."""
    before = text[max(0, start - back):start]
    cuts = list(_SENT_END.finditer(before))
    if cuts:
        before = before[cuts[-1].end():]
    after = text[end:end + fwd]
    m = _SENT_END.search(after)
    if m:
        after = after[:m.start()]
    return before.lower(), after.lower()


def _nearest_role(before: str, after: str) -> tuple[str | None, str | None]:
    """(role, fee_type) for one amount, from the closest cue word on either side."""
    best = (10 ** 6, None, None)
    for role, cues in _ROLE_CUES.items():
        for c in cues:
            i = before.rfind(c)
            if i >= 0:
                d = len(before) - (i + len(c))
                if d < best[0]:
                    best = (d, role, None)
            if role == "difference":
                j = after.find(c)
                if 0 <= j < best[0]:
                    best = (j, role, None)
    for fee, cues in _FEE_CUES.items():
        for c in cues:
            j = after.find(c)
            if 0 <= j and j < best[0]:
                best = (j, "charged", fee)
            i = before.rfind(c)
            if i >= 0:
                d = len(before) - (i + len(c))
                if d < best[0]:
                    best = (d, "charged", fee)
    return best[1], best[2]


def _fee_type(text: str) -> str | None:
    low = text.lower()
    for fee, cues in _FEE_CUES.items():
        if any(c in low for c in cues):
            return fee
    return None


# ---------------------------------------------------------------- places

# Local names for the places in the trip fixtures. Keys must be fixture place names.
PLACE_ALIASES: dict[str, tuple[str, ...]] = {
    "Changi Airport T3": ("Changi Airport Terminal 3", "Changi T3", "樟宜机场", "樟宜機場", "樟宜机场第三航站楼",
                          "lapangan terbang Changi", "சாங்கி விமான நிலையம்"),
    "Orchard Central": ("乌节中心", "烏節中心", "ஆர்ச்சர்ட் சென்ட்ரல்"),
    "Orchard MRT": ("Orchard station", "乌节地铁站", "乌节站"),
    "Tiong Bahru Plaza": ("中峇鲁广场", "中峇魯廣場", "中峇鲁", "தியோங் பாரு பிளாசா"),
    "VivoCity": ("Vivo City", "怡丰城", "怡豐城"),
    "Bugis Junction": ("白沙浮广场", "武吉士"),
    "Marina Bay Sands": ("MBS", "滨海湾金沙", "濱海灣金沙", "金沙酒店"),
    "Changi Business Park": ("CBP", "樟宜商业园"),
    "Clarke Quay": ("克拉码头", "克拉碼頭"),
    "Tampines Mall": ("淡滨尼广场", "淡滨尼"),
    "Tanjong Pagar Centre": ("丹戎巴葛中心", "丹戎巴葛"),
    "HarbourFront Centre": ("港湾中心", "港灣中心"),
}


def _is_cjk_or_tamil(s: str) -> bool:
    return bool(re.search(r"[㐀-鿿஀-௿]", s))


def _form_regex(form: str) -> re.Pattern:
    chars = [re.escape(c) for c in re.sub(r"[\s\-'’]", "", form)]
    body = r"[\s\-'’]*".join(chars)
    if _is_cjk_or_tamil(form):
        return re.compile(body, re.I)
    return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])", re.I)


@lru_cache(maxsize=8)
def _place_forms(places: tuple[str, ...]) -> tuple:
    """(canonical, form, coverage, regex) for every way a fixture place can be written.

    A shortened form ("Changi Airport" for "Changi Airport T3") is only used when no other place
    starts the same way ("Orchard" alone could be Orchard Central or Orchard MRT, so it is not used).
    """
    forms = []
    lows = [p.lower().split() for p in places]
    for p, toks in zip(places, lows):
        forms.append((p, p, 1.0))
        for k in range(len(toks) - 1, 0, -1):
            pre = toks[:k]
            if any(o[:k] == pre for o in lows if o != toks):
                continue
            if k == 1 and len(pre[0]) < 5:
                continue
            forms.append((p, " ".join(pre), round(k / len(toks), 2)))
        for a in PLACE_ALIASES.get(p, ()):
            forms.append((p, a, 1.0))
    return tuple((p, f, c, _form_regex(f)) for p, f, c in forms)


def default_places() -> tuple[str, ...]:
    from app.tools.fixtures import list_place_names
    return tuple(list_place_names())


_DROP_BEFORE = re.compile(r"(?:\bto|\btowards|\btill|\buntil|\bdrop(?:ped)?(?:\s+me)?(?:\s+off)?(?:\s+at)?|\bke|\bsampai|\bhingga|"
                          r"到|去|往|至|送到|送我到)\s*(?:the\s+)?$", re.I)
# "never came to X" / "tidak datang ke X": X is where the rider was waiting, i.e. the pickup
_ARRIVE_BEFORE = re.compile(r"(?:\bcame|\bcome|\bcoming|\barrive[ds]?|\bturn(?:ed)?\s+up|\bshow(?:ed)?\s+up|\bdatang|\btiba)"
                            r"\s+(?:to|at|ke|di)\s*(?:the\s+)?$", re.I)
_PICK_BEFORE = re.compile(r"(?:\bfrom|\bat|\bpick\s*-?\s*up(?:\s+point)?(?:\s+at)?|\bin front of|\boutside|\bdari|\bdi|"
                          r"从|在|由|于)\s*(?:the\s+)?$", re.I)


def find_places(text: str, places: tuple[str, ...] | None = None) -> list[dict]:
    """Fixture place names mentioned in the story: [{place, surface, start, end, coverage, role}].

    role is "pickup" / "dropoff" when the wording says so ("from X", "to X", "dari X ke Y", "从X到Y",
    "X இலிருந்து"), else None.
    """
    text = text or ""
    places = places or default_places()
    hits = []
    for p, form, cov, rx in _place_forms(tuple(places)):
        for m in rx.finditer(text):
            hits.append({"place": p, "surface": m.group(0), "start": m.start(), "end": m.end(), "coverage": cov})
    # typo-tolerant pass on Latin names ("Orchard Centrel", "Tiong Baru Plaza")
    found = {h["place"] for h in hits}
    words = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[A-Za-z0-9']+", text)]
    for p in places:
        if p in found or _is_cjk_or_tamil(p):
            continue
        n = len(p.split())
        for i in range(0, max(0, len(words) - n + 1)):
            seg = words[i:i + n]
            cand = " ".join(w for w, _, _ in seg)
            if difflib.SequenceMatcher(None, cand.lower(), p.lower()).ratio() >= 0.86:
                hits.append({"place": p, "surface": text[seg[0][1]:seg[-1][2]], "start": seg[0][1],
                             "end": seg[-1][2], "coverage": 0.9})
                break
    # overlapping hits: keep the most complete one
    hits.sort(key=lambda h: (-h["coverage"], -(h["end"] - h["start"])))
    kept: list[dict] = []
    for h in hits:
        if not any(h["start"] < k["end"] and k["start"] < h["end"] for k in kept):
            kept.append(h)
    kept.sort(key=lambda h: h["start"])
    for h in kept:
        before = text[max(0, h["start"] - 22):h["start"]]
        after = text[h["end"]:h["end"] + 12]
        if _ARRIVE_BEFORE.search(before):
            h["role"] = "pickup"
        elif _DROP_BEFORE.search(before) or after.lstrip().startswith(("வரை", "க்கு")):
            h["role"] = "dropoff"
        elif _PICK_BEFORE.search(before) or after.lstrip().startswith(("இலிருந்து", "இல் இருந்து", "லிருந்து", "இல்")):
            h["role"] = "pickup"
        else:
            h["role"] = None
    # "Bugis Junction to Marina Bay Sands": two unlabelled places in a row read as pickup then drop-off
    distinct = []
    for h in kept:
        if h["place"] not in [d["place"] for d in distinct]:
            distinct.append(h)
    if len(distinct) == 2 and not any(d["role"] for d in distinct):
        between = text[distinct[0]["end"]:distinct[1]["start"]]
        if re.search(r"\bto\b|→|->|\bke\b|到|வரை", between, re.I):
            distinct[0]["role"], distinct[1]["role"] = "pickup", "dropoff"
    return kept


# ---------------------------------------------------------------- times

_MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
_MONTHS.update({"sept": 9, "ogos": 8, "mei": 5, "okt": 10, "dis": 12, "januari": 1, "februari": 2, "mac": 3, "julai": 7})
_T_CLOCK = re.compile(r"(?<![\d$.])(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)(?![a-z])"
                      r"|(?<![\d$.])(\d{1,2}):(\d{2})(?!\d)", re.I)
_T_ZH = re.compile(r"(凌晨|早上|上午|中午|下午|傍晚|晚上|夜里)?\s*(\d{1,2})\s*[点點](?:\s*(半)|\s*(\d{1,2})\s*分)?")
_D_DM = re.compile(r"(?<![\d$.])(\d{1,2})(?:st|nd|rd|th)?\s+(jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|"
                   r"nov\w*|dec\w*|ogos|mei|okt|dis|mac|julai)\b", re.I)
_D_MD = re.compile(r"\b(jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
_D_SLASH = re.compile(r"(?<![\d$.])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?!\d)")
_D_ZH = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号號]")
_PARTS = {
    "morning": ("this morning", "morning", "pagi", "早上", "上午", "காலை"),
    "afternoon": ("afternoon", "tengah hari", "petang", "下午", "中午", "மதியம்"),
    "evening": ("evening", "tonight", "last night", "night", "malam", "晚上", "傍晚", "昨晚", "夜里", "இரவு", "மாலை"),
    "late_night": ("midnight", "凌晨", "tengah malam", "நள்ளிரவு"),
}


_WEEKDAYS = {
    0: ("monday", "isnin", "星期一", "周一", "礼拜一"), 1: ("tuesday", "selasa", "星期二", "周二", "礼拜二"),
    2: ("wednesday", "rabu", "星期三", "周三", "礼拜三"), 3: ("thursday", "khamis", "星期四", "周四", "礼拜四"),
    4: ("friday", "jumaat", "星期五", "周五", "礼拜五"), 5: ("saturday", "sabtu", "星期六", "周六", "礼拜六"),
    6: ("sunday", "ahad", "星期日", "星期天", "周日", "礼拜天"),
}


def _month(s: str) -> int | None:
    s = s.lower()
    return _MONTHS.get(s) or _MONTHS.get(s[:4]) or _MONTHS.get(s[:3])


def extract_times(text: str) -> list[dict]:
    """Time and date mentions: [{text, hour?, minute?, day?, month?, part?}] in story order."""
    text = text or ""
    out: list[dict] = []
    taken: list[tuple[int, int]] = []

    def push(m, **kw):
        if _overlaps((m.start(), m.end()), taken):
            return
        taken.append((m.start(), m.end()))
        out.append({"text": m.group(0).strip(), "_pos": m.start(), **kw})

    for m in _T_CLOCK.finditer(text):
        if m.group(3):
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            ap = m.group(3).lower().replace(".", "")
            if h <= 12:
                h = (h % 12) + (12 if ap == "pm" else 0)
                push(m, hour=h, minute=mi)
        elif int(m.group(4)) < 24 and int(m.group(5)) < 60:
            push(m, hour=int(m.group(4)), minute=int(m.group(5)))
    for m in _T_ZH.finditer(text):
        h = int(m.group(2))
        part = m.group(1) or ""
        if part in ("下午", "傍晚", "晚上", "夜里") and h < 12:
            h += 12
        if h < 24:
            push(m, hour=h, minute=30 if m.group(3) else int(m.group(4) or 0))
    for m in _D_DM.finditer(text):
        mo = _month(m.group(2))
        if mo:
            push(m, day=int(m.group(1)), month=mo)
    for m in _D_MD.finditer(text):
        mo = _month(m.group(1))
        if mo:
            push(m, day=int(m.group(2)), month=mo)
    for m in _D_ZH.finditer(text):
        push(m, day=int(m.group(2)), month=int(m.group(1)))
    for m in _D_SLASH.finditer(text):
        d, mo = int(m.group(1)), int(m.group(2))     # Singapore writes day/month
        if 1 <= d <= 31 and 1 <= mo <= 12:
            push(m, day=d, month=mo)
    low = text.lower()
    for part, words in _PARTS.items():
        for w in sorted(words, key=len, reverse=True):
            i = low.find(w.lower())
            if i >= 0 and not _overlaps((i, i + len(w)), taken):
                taken.append((i, i + len(w)))
                out.append({"text": text[i:i + len(w)], "_pos": i, "part": part})
                break
    for w in ("yesterday", "today", "just now", "semalam", "hari ini", "tadi", "昨天", "今天", "刚才", "நேற்று", "இன்று"):
        i = low.find(w)
        if i >= 0 and not _overlaps((i, i + len(w)), taken):
            taken.append((i, i + len(w)))
            ago = 1 if w in ("yesterday", "semalam", "昨天", "நேற்று") else 0
            out.append({"text": text[i:i + len(w)], "_pos": i, "days_ago": ago})
    for wd, words in _WEEKDAYS.items():
        for w in words:
            m = re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low) if w.isascii() else (re.search(re.escape(w), text))
            if m and not _overlaps((m.start(), m.end()), taken):
                taken.append((m.start(), m.end()))
                out.append({"text": text[m.start():m.end()], "_pos": m.start(), "weekday": wd})
                break
    out.sort(key=lambda x: x.pop("_pos"))
    return out


# ---------------------------------------------------------------- actions, language

# (who, cue words, English label, Chinese label). A label is emitted only when a cue is in the story.
_ACTIONS = [
    ("driver", ("detour", "longer route", "long way", "went through", "round and round", "go round", "went round",
                "out of the way", "绕", "兜圈", "jalan jauh", "சுற்றி", "நீண்ட வழி"),
     "took a longer route", "绕路"),
    ("driver", ("did not inform", "didn't inform", "did not tell", "didn't tell", "never told", "never informed",
                "tidak memberitahu", "tak beritahu", "没告诉我", "没有告诉我"),
     "did not tell the rider about the change", "未告知乘客变更"),
    ("driver", ("never showed", "never came", "didn't show", "did not show", "never turn up", "never turned up",
                "didn't turn up", "did not turn up", "nobody came", "no one came", "didn't arrive", "did not arrive",
                "never arrived", "never arrive", "没来", "没出现", "没到", "tidak datang", "tak datang", "tak sampai",
                "வரவில்லை"),
     "did not show up", "未到场"),
    ("driver", ("speeding", "too fast", "speed", "超速", "开太快", "开得太快", "laju", "வேக"),
     "was speeding", "超速"),
    ("driver", ("red light", "闯红灯", "lampu merah", "சிவப்பு"), "ran a red light", "闯红灯"),
    ("driver", ("shouted", "yelled", "scolded", "screamed", "骂", "吼", "jerit", "marah", "கத்த"),
     "shouted at the rider", "对乘客大声吼叫"),
    ("driver", ("threat", "威胁", "ancam", "மிரட்ட"), "threatened the rider", "威胁乘客"),
    ("driver", ("harass", "touched me", "grope", "骚扰", "ganggu"), "harassed the rider", "骚扰乘客"),
    ("driver", ("driver cancelled", "driver canceled", "司机取消", "pemandu batal"), "cancelled the trip", "取消了行程"),
    ("rider", ("waited", "waiting", "i wait", "等了", "等半天", "等很久", "tunggu", "காத்திருந்த"),
     "waited for the driver", "等候司机"),
    ("rider", ("on time", "准时", "tepat pada masa"), "was at the pickup point on time", "准时到达上车点"),
    ("rider", ("slow down", "开慢", "慢一点", "慢点", "perlahan"), "asked the driver to slow down", "要求司机减速"),
    ("rider", ("did not spill", "didn't spill", "never spilled", "did not dirty", "didn't dirty", "not dirty",
               "car was clean", "没有弄脏", "没弄脏", "tidak kotor", "tak kotor", "tidak tumpah"),
     "says they did not dirty the car", "称没有弄脏车辆"),
    ("rider", ("couldn't find the car", "could not find the car", "never saw any car", "never saw the car",
               "找不到车", "没看到车", "tak nampak kereta", "tidak nampak kereta"),
     "could not find the car", "找不到车辆"),
    ("rider", ("called the driver", "messaged the driver", "texted the driver", "打电话给司机", "给司机发",
               "call pemandu", "telefon pemandu"),
     "contacted the driver", "联系过司机"),
    ("rider", ("nobody told", "no one told", "was not informed", "wasn't informed", "not informed", "wasn't told",
               "was not told", "没人告诉", "没有人告诉", "没通知", "没有通知", "tiada siapa beritahu"),
     "was not told about a price or route change", "未被告知价格或路线变更"),
]

_MALAY = ("saya", "tidak", "tak", "pemandu", "dikenakan", "tetapi", "kereta", "yang", "dengan", "sudah", "tunggu", "caj")
_SINGLISH = ("lah", "leh", "sia", "lor", "meh", "liao", "alamak", "wah", "aiyo", "kena", "one leh", "can or not", "uncle")


def detect_language(text: str) -> str:
    """en / en-SG (Singlish) / ms / ta / zh."""
    t = text or ""
    if re.search(r"[஀-௿]", t):
        return "ta"
    if len(re.findall(r"[㐀-鿿]", t)) >= 2:
        return "zh"
    words = re.findall(r"[a-z']+", t.lower())
    if sum(w in _MALAY for w in words) >= 2:
        return "ms"
    if any(w in words for w in _SINGLISH if " " not in w) or any(p in t.lower() for p in _SINGLISH if " " in p):
        return "en-SG"
    return "en"


# ---------------------------------------------------------------- facts

FACT_FIELDS = ("quoted_amount", "charged_amount", "claimed_difference", "fee_type", "pickup_place", "dropoff_place",
               "time_mentions", "driver_actions", "rider_actions", "safety_indicators", "detected_language")


def empty_facts() -> dict:
    return {k: ([] if k in ("time_mentions", "driver_actions", "rider_actions", "safety_indicators") else None)
            for k in FACT_FIELDS}


def extract_facts(text: str, lang: str = "en", places: tuple[str, ...] | None = None) -> dict:
    """Rule-based extracted_facts for a story. Fields the story does not state are null / []."""
    from app.agents.intake import detect_safety
    text = text or ""
    f = empty_facts()
    nums = extract_numbers(text)
    for a in nums["amounts"]:
        before, after = _clause_window(text, a["start"], a["end"])
        role, fee = _nearest_role(before, after)
        key = {"quote": "quoted_amount", "charged": "charged_amount", "difference": "claimed_difference"}.get(role)
        if key and f[key] is None:
            f[key] = a["value"]
        if fee and not f["fee_type"]:
            f["fee_type"] = fee
    f["fee_type"] = f["fee_type"] or _fee_type(text)
    for h in find_places(text, places):
        if h["role"] == "pickup" and not f["pickup_place"]:
            f["pickup_place"] = h["surface"]
        elif h["role"] == "dropoff" and not f["dropoff_place"]:
            f["dropoff_place"] = h["surface"]
    f["time_mentions"] = [t["text"] for t in extract_times(text)]
    low = text.lower()
    for who, cues, en, zh in _ACTIONS:
        if any(c in low for c in cues):
            f[f"{who}_actions"].append(L(lang, en, zh))
    f["safety_indicators"] = detect_safety(text)
    f["detected_language"] = detect_language(text)
    return f


def derive_requested_amount(f: dict) -> float | None:
    """What the rider is asking back, from the amounts the story states (never from records)."""
    if f.get("claimed_difference") is not None:
        return f["claimed_difference"]
    if f.get("fee_type") and f.get("charged_amount") is not None:
        return f["charged_amount"]
    q, c = f.get("quoted_amount"), f.get("charged_amount")
    if q is not None and c is not None and c > q:
        return round(c - q, 2)
    return None


def story_numbers(text: str) -> list[float]:
    """Every number written in the story (used to check that a model did not invent one)."""
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text or "")]


def ground_facts(facts: dict, text: str, rule_facts: dict, places: tuple[str, ...] | None = None) -> dict:
    """Drop anything a model put in extracted_facts that the story does not support."""
    nums = story_numbers(text)
    g = dict(facts)
    for k in ("quoted_amount", "charged_amount", "claimed_difference"):
        v = g.get(k)
        if v is not None and not any(abs(v - n) < 0.011 for n in nums):
            g[k] = rule_facts.get(k)
    low = (text or "").lower()
    seen = {h["place"] for h in find_places(text, places)}
    for k in ("pickup_place", "dropoff_place"):
        v = g.get(k)
        if v and v.lower() not in low:
            canon = {h["place"] for h in find_places(v, places)}
            if not (canon & seen):
                g[k] = rule_facts.get(k)
    tm = [t for t in (g.get("time_mentions") or []) if isinstance(t, str) and t.strip() and t.lower() in low]
    g["time_mentions"] = tm or rule_facts.get("time_mentions", [])
    for k in ("driver_actions", "rider_actions"):
        if not g.get(k):
            g[k] = rule_facts.get(k, [])
    if g.get("fee_type") not in (None, "cleaning_fee", "cancellation_fee", "damage_fee"):
        g["fee_type"] = rule_facts.get("fee_type")
    g["detected_language"] = g.get("detected_language") or rule_facts.get("detected_language")
    return g


def missing_info(dtype: str, f: dict, lang: str = "en") -> list[str]:
    """Things that would help the case but the story did not say."""
    out: list[str] = []

    def need(cond, en, zh):
        if cond:
            out.append(L(lang, en, zh))

    need(not f.get("time_mentions"), "Date or time of the trip", "行程的日期或时间")
    if dtype == "route_deviation":
        need(not f.get("pickup_place"), "Pickup location", "上车地点")
        need(not f.get("dropoff_place"), "Drop-off location", "下车地点")
        need(f.get("charged_amount") is None, "Fare you were charged", "实际被收取的车费")
        need(f.get("quoted_amount") is None, "Fare you expected (quote or usual price)", "预期车费（报价或平时价格）")
    elif dtype == "no_show_charge":
        need(not f.get("pickup_place"), "Where you were waiting", "你等候的地点")
        need(f.get("charged_amount") is None, "Cancellation fee amount", "取消费金额")
        need(not any(k in " ".join(f.get("rider_actions") or []) for k in ("waited", "等候")),
             "How long you waited", "你等了多久")
        need(not any(k in " ".join(f.get("rider_actions") or []) for k in ("contacted", "联系")),
             "Whether you or the driver tried to call or message", "你或司机是否打过电话或发过消息")
    elif dtype == "fare_dispute":
        need(f.get("quoted_amount") is None, "Upfront quote shown at booking", "下单时显示的预付报价")
        need(f.get("charged_amount") is None, "Final fare charged", "最终收取的车费")
    elif dtype == "property_damage":
        need(f.get("charged_amount") is None, "Amount of the cleaning or damage fee", "清洁费或损坏费金额")
    elif dtype == "safety_incident":
        need(not f.get("pickup_place") and not f.get("dropoff_place"), "Where it happened", "事发地点")
        need(not f.get("driver_actions"), "What the driver did", "司机具体做了什么")
    if dtype != "safety_incident":
        need(derive_requested_amount(f) is None, "Amount you want refunded", "希望退还的金额")
    return out
