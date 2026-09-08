"""Work item 4: emit every copy key the engine can ask, plus draft labels.

The web client auto-skips any question whose keys have no authored copy, so a
live interview currently ends at the sign: the decan and mover-house channels
have no text. This is not a code problem and the engine cannot fix it, but the
engine is the only thing that knows the complete key list and what each key has
to *mean* - which partition it distinguishes from which.

Two artefacts:
  * astro_engine/data/copy_manifest.json - every key, per channel, with the
    distinction it draws. Generated, complete, machine-readable.
  * docs/copy_drafts.md - one table for the owner to read and correct. Drafts
    are marked `draft` and the web imports only rows marked `approved`.

    python benchmarks/build_copy_manifest.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import core, interview  # noqa: E402

MANIFEST = (
    pathlib.Path(__file__).resolve().parent.parent
    / "astro_engine" / "data" / "copy_manifest.json"
)
DRAFTS = pathlib.Path(__file__).resolve().parent.parent / "docs" / "copy_drafts.md"

LOCALES = ("en", "ru", "uk", "de")

# --------------------------------------------------------------------------
# Meaning tables. These describe what a key has to distinguish, which is the
# part the owner cannot reconstruct from the key name alone.
# --------------------------------------------------------------------------

HOUSE_MEANING = {
    1: ("the body and first impression", "how you come across before you speak"),
    2: ("what you own and earn", "money, possessions, and what you value"),
    3: ("everyday exchange", "siblings, short trips, talk and study"),
    4: ("home and origins", "family, the place you come from, the end of things"),
    5: ("what you make and enjoy", "children, play, romance, performance"),
    6: ("work and health", "daily duty, service, illness and routine"),
    7: ("one-to-one", "partnership, marriage, open opponents"),
    8: ("what is shared or lost", "other people's money, crisis, death, the hidden"),
    9: ("the far and the abstract", "long journeys, belief, higher study, law"),
    10: ("standing in the world", "career, reputation, the public role"),
    11: ("the wider circle", "friends, groups, hopes and alliances"),
    12: ("what is withdrawn", "seclusion, hospitals, confinement, private undoing"),
}

PLANET_MEANING = {
    "sun": "vitality and purpose",
    "moon": "feeling, habit and need",
    "mercury": "thinking and talking",
    "venus": "affection, taste and worth",
    "mars": "drive, anger and effort",
    "jupiter": "growth, luck and belief",
    "saturn": "limit, duty and time",
    "uranus": "disruption and independence",
    "neptune": "dissolution, longing and imagination",
    "pluto": "compulsion, power and remaking",
}

ELEMENT_DRAFT = {
    "element_fire": {
        "en": "You act first and think about it afterwards; you warm up a room.",
        "ru": "Вы сначала действуете, потом обдумываете; с вами становится теплее.",
        "uk": "Ви спершу дієте, а потім обмірковуєте; з вами стає тепліше.",
        "de": "Sie handeln zuerst und denken danach nach; Sie wärmen einen Raum auf.",
    },
    "element_earth": {
        "en": "You start slowly and finish what you start; you trust what you can touch.",
        "ru": "Вы медленно начинаете и доводите до конца; доверяете тому, что можно потрогать.",
        "uk": "Ви повільно починаєте й доводите до кінця; довіряєте тому, що можна торкнутися.",
        "de": "Sie beginnen langsam und bringen zu Ende; Sie trauen dem Greifbaren.",
    },
    "element_air": {
        "en": "You think out loud and need to talk things through before they are real.",
        "ru": "Вы думаете вслух: пока не проговорите, оно как будто не существует.",
        "uk": "Ви думаєте вголос: доки не проговорите, воно ніби не існує.",
        "de": "Sie denken laut; erst im Gespräch wird eine Sache wirklich.",
    },
    "element_water": {
        "en": "You read the mood of a room before anything is said.",
        "ru": "Вы считываете настроение вокруг раньше, чем что-то произнесено.",
        "uk": "Ви зчитуєте настрій навколо раніше, ніж щось сказано.",
        "de": "Sie spüren die Stimmung im Raum, bevor etwas gesagt wird.",
    },
}

MODALITY_DRAFT = {
    "modality_cardinal": {
        "en": "You start things. Beginnings energise you; finishing is the effort.",
        "ru": "Вы начинаете. Начало вдохновляет, а вот доводить до конца — труд.",
        "uk": "Ви починаєте. Початок надихає, а доводити до кінця — праця.",
        "de": "Sie fangen an. Anfänge beleben Sie; das Beenden ist die Mühe.",
    },
    "modality_fixed": {
        "en": "You hold a position. Once set on something you are hard to move.",
        "ru": "Вы держите позицию. Если уж на чём-то встали — сдвинуть трудно.",
        "uk": "Ви тримаєте позицію. Якщо вже на чомусь стали — зрушити важко.",
        "de": "Sie halten eine Position. Einmal entschieden, sind Sie schwer zu bewegen.",
    },
    "modality_mutable": {
        "en": "You change tack easily. Adapting costs you little; committing costs more.",
        "ru": "Вы легко меняете курс. Приспособиться просто, а вот выбрать одно — сложнее.",
        "uk": "Ви легко змінюєте курс. Пристосуватися просто, а обрати одне — складніше.",
        "de": "Sie wechseln leicht den Kurs. Anpassen fällt leicht, Festlegen schwerer.",
    },
}

SIGN_PORTRAIT_DRAFT = {
    "aries": ("Direct, quick to start, visibly impatient with delay.",
              "Прямой, быстро начинает, заметно не терпит промедления.",
              "Прямий, швидко починає, помітно не терпить зволікання.",
              "Direkt, schnell im Anfangen, sichtbar ungeduldig."),
    "taurus": ("Steady, unhurried, hard to rush and harder to move.",
               "Устойчивый, неспешный: его не поторопить и не сдвинуть.",
               "Стійкий, неквапливий: його не поквапити й не зрушити.",
               "Ruhig, unaufgeregt, schwer zu drängen und noch schwerer zu bewegen."),
    "gemini": ("Quick, talkative, several things going at once.",
               "Быстрый, разговорчивый, всегда несколько дел сразу.",
               "Швидкий, говіркий, завжди кілька справ водночас.",
               "Schnell, gesprächig, mehrere Dinge gleichzeitig."),
    "cancer": ("Guarded at first, warm once inside; remembers everything.",
               "Сначала настороженный, потом тёплый; помнит всё.",
               "Спершу насторожений, потім теплий; памʼятає все.",
               "Zunächst zurückhaltend, dann warm; vergisst nichts."),
    "leo": ("Warm, visible, carries a room without trying.",
            "Тёплый, заметный, держит внимание без усилий.",
            "Теплий, помітний, тримає увагу без зусиль.",
            "Warm, sichtbar, füllt einen Raum ohne Anstrengung."),
    "virgo": ("Precise, useful, notices what is slightly wrong.",
              "Точный, полезный, замечает, что чуть-чуть не так.",
              "Точний, корисний, помічає, що трохи не так.",
              "Genau, nützlich, bemerkt, was leicht daneben ist."),
    "libra": ("Even, pleasant, weighs both sides before committing.",
              "Ровный, приятный, взвешивает обе стороны прежде чем решить.",
              "Рівний, приємний, зважує обидві сторони перш ніж вирішити.",
              "Ausgeglichen, angenehm, wägt beide Seiten ab."),
    "scorpio": ("Reserved and intent; says little and misses nothing.",
                "Сдержанный и пристальный: говорит мало, не упускает ничего.",
                "Стриманий і пильний: говорить мало, не проминає нічого.",
                "Zurückhaltend und eindringlich; sagt wenig, übersieht nichts."),
    "sagittarius": ("Open, restless, drawn to whatever is further away.",
                    "Открытый, непоседливый, тянется к тому, что подальше.",
                    "Відкритий, непосидючий, тягнеться до того, що далі.",
                    "Offen, ruhelos, angezogen von dem, was weiter weg ist."),
    "capricorn": ("Contained, serious, plays a long game.",
                  "Сдержанный, серьёзный, играет вдолгую.",
                  "Стриманий, серйозний, грає надовго.",
                  "Beherrscht, ernst, denkt langfristig."),
    "aquarius": ("Friendly but separate; holds an unusual position calmly.",
                 "Дружелюбный, но отдельный; спокойно держит необычную позицию.",
                 "Дружній, але окремий; спокійно тримає незвичну позицію.",
                 "Freundlich, aber distanziert; hält ruhig eine ungewöhnliche Position."),
    "pisces": ("Soft-edged, absorbing, hard to pin to one outline.",
               "С размытыми краями, впитывающий, его трудно очертить одним контуром.",
               "З розмитими краями, вбирає все, його важко окреслити одним контуром.",
               "Weiche Konturen, aufnehmend, schwer auf eine Form festzulegen."),
}

DECAN_ORDINAL = {"first": "the first third", "second": "the middle third",
                 "third": "the last third"}

# --------------------------------------------------------------------------
# v3.2: copy ATOMS, Russian master.
#
# v3.1 emitted 315 template-generated English rows - one per planet x house x
# facet - which is 315 sentences to correct when there are only 22 ideas
# underneath them. These are those ideas, in Russian, for the owner to
# correct. Translation to EN/DE/UK happens later and only from approved
# Russian rows.
# --------------------------------------------------------------------------

HOUSE_ATOM_RU = {
    1: "тело, внешность и первое впечатление — каким вас видят до того, как вы заговорили",
    2: "деньги, имущество и то, что вы считаете своим и ценным",
    3: "повседневный обмен: братья и сёстры, короткие поездки, разговоры, учёба",
    4: "дом, семья и происхождение — место, откуда вы, и то, чем всё заканчивается",
    5: "дети, творчество, игра, влюблённость и всё, что вы делаете напоказ",
    6: "работа изо дня в день, обязанности, служба и здоровье",
    7: "отношения один на один: брак, партнёрство, открытые противники",
    8: "чужие деньги, общее имущество, кризис, утрата и всё скрытое",
    9: "дальнее и отвлечённое: долгие путешествия, вера, высшее образование, право",
    10: "положение в мире: карьера, репутация, публичная роль",
    11: "круг общения: друзья, сообщества, надежды и союзы",
    12: "то, что скрыто от глаз: уединение, больницы, изоляция, тайные потери",
}

PLANET_ATOM_RU = {
    "sun": "жизненная сила и то, ради чего вы живёте",
    "moon": "чувства, привычки и то, в чём вы нуждаетесь",
    "mercury": "мышление, речь и обмен сведениями",
    "venus": "привязанность, вкус и чувство ценности",
    "mars": "напор, злость и усилие",
    "jupiter": "рост, удача и убеждения",
    "saturn": "ограничение, долг и время",
    "uranus": "слом привычного и независимость",
    "neptune": "растворение, тоска и воображение",
    "pluto": "одержимость, власть и переделка себя",
}

# Thirty-six decan appearance traits: sign x first/second/third third.
DECAN_ATOM_RU = {
    ("aries", "first"): "резкие черты, быстрый прямой взгляд, порывистые движения",
    ("aries", "second"): "плотное сложение, тяжеловатая челюсть, упрямый разворот плеч",
    ("aries", "third"): "сухощавость, беспокойные руки, быстрая смена выражения",
    ("taurus", "first"): "крепкая шея, спокойное лицо, неспешная тяжёлая походка",
    ("taurus", "second"): "округлые линии, мягкий низкий голос, покатые плечи",
    ("taurus", "third"): "плотное тело при подвижном лице, внимательные глаза",
    ("gemini", "first"): "длинные руки, лёгкая кость, подвижная мимика",
    ("gemini", "second"): "сухое сложение, быстрый взгляд, частые жесты при речи",
    ("gemini", "third"): "неровные черты, юношеский вид дольше положенного",
    ("cancer", "first"): "мягкий овал лица, широко посаженные глаза, покатые плечи",
    ("cancer", "second"): "полнота в верхней части тела, переменчивое выражение",
    ("cancer", "third"): "бледная кожа, тихие движения, взгляд немного в сторону",
    ("leo", "first"): "прямая осанка, крупная голова, заметная посадка головы",
    ("leo", "second"): "густые волосы, тёплый открытый взгляд, широкая грудная клетка",
    ("leo", "third"): "лёгкая полнота, живая мимика, привычка держать спину",
    ("virgo", "first"): "аккуратное сухое сложение, внимательный сдержанный взгляд",
    ("virgo", "second"): "тонкие черты, ровная кожа, скупые точные движения",
    ("virgo", "third"): "невысокий рост, быстрая речь, привычка поправлять детали",
    ("libra", "first"): "правильные черты, ровная осанка, приятная мягкость лица",
    ("libra", "second"): "округлое лицо, ямочки, ленивая грация в движениях",
    ("libra", "third"): "высокий рост, тонкая кость, чуть отстранённое выражение",
    ("scorpio", "first"): "тяжёлые брови, пристальный взгляд, сдержанные движения",
    ("scorpio", "second"): "плотное сложение, низкий голос, неподвижное лицо",
    ("scorpio", "third"): "резкий профиль, бледность, привычка смотреть исподлобья",
    ("sagittarius", "first"): "высокий рост, длинные ноги, открытая улыбка",
    ("sagittarius", "second"): "крупное сложение, громкий смех, размашистые жесты",
    ("sagittarius", "third"): "худощавость, беспокойная посадка, взгляд поверх собеседника",
    ("capricorn", "first"): "сухое сложение, выраженные скулы, сдержанное лицо",
    ("capricorn", "second"): "тёмные волосы, серьёзное выражение, экономные движения",
    ("capricorn", "third"): "невысокий плотный сложение, ранняя строгость в лице",
    ("aquarius", "first"): "высокий рост, необычные пропорции, спокойный прямой взгляд",
    ("aquarius", "second"): "широкий лоб, отстранённое выражение, ровная осанка",
    ("aquarius", "third"): "лёгкая кость, рассеянный взгляд, неожиданные жесты",
    ("pisces", "first"): "мягкие расплывчатые черты, большие влажные глаза",
    ("pisces", "second"): "покатые плечи, тихий голос, текучие движения",
    ("pisces", "third"): "бледность, переменчивое выражение, взгляд как бы внутрь",
}

# The sentences that compose a question out of the atoms above.
TEMPLATE_RU = {
    "mover_house.life_area": (
        "Где в своей жизни вы сильнее чувствуете [тема планеты] — "
        "в сфере «[сфера A]» или в сфере «[сфера B]»?"
    ),
    "mover_house.episode": (
        "Вспомните период, когда [тема планеты] проявлялась сильнее всего. "
        "Это было связано скорее со сферой «[сфера A]» или со сферой «[сфера B]»?"
    ),
    "decan.manner": (
        "Что ближе к тому, как вы себя держите: «[черта декана A]» "
        "или «[черта декана B]»?"
    ),
    "decan.appearance": (
        "Что ближе к вашей внешности: «[черта декана A]» или «[черта декана B]»?"
    ),
}



def build_manifest() -> dict:
    entries = []

    for tag_id in interview.ELEMENT_TAGS + interview.MODALITY_TAGS:
        tag = interview.TRAIT_TAGS[tag_id]
        channel = tag["channel"]
        strong = sorted(
            [s for s, v in tag["likelihood"].items() if v >= 0.6]
        )
        for kind in ("label_key", "paraphrase_key"):
            entries.append({
                "key": tag[kind],
                "channel": channel,
                "variant": "a" if kind == "label_key" else "b",
                "answer_id": tag_id,
                "distinguishes": f"{', '.join(strong)} from the other signs",
            })

    for sign in interview.TRAIT_SIGNS:
        for facet in ("portrait", "portrait_contrast"):
            entries.append({
                "key": f"sign.{sign}.{facet}",
                "channel": "sign_portrait",
                "variant": "a" if facet == "portrait" else "b",
                "answer_id": sign,
                "distinguishes": f"{sign} rising from the one other sign offered",
            })

    for sign in interview.TRAIT_SIGNS:
        for decan in interview.DECAN_NAMES:
            for facet in ("manner", "appearance"):
                entries.append({
                    "key": f"decan.{sign}.{decan}.{facet}",
                    "channel": "decan",
                    "variant": "a" if facet == "manner" else "b",
                    "answer_id": f"{sign}_{decan}",
                    "distinguishes": (
                        f"{DECAN_ORDINAL[decan]} of {sign} rising from the "
                        "other thirds of the same sign"
                    ),
                })

    for planet, _ in core.PLANETS:
        for house in range(1, 13):
            area, detail = HOUSE_MEANING[house]
            for facet in ("life_area", "episode"):
                entries.append({
                    "key": f"planet.{planet}.house.{house}.{facet}",
                    "channel": "mover_house",
                    "variant": "a" if facet == "life_area" else "b",
                    "answer_id": str(house),
                    "distinguishes": (
                        f"{planet} ({PLANET_MEANING[planet]}) in house {house} "
                        f"- {area}: {detail} - from the same planet in the "
                        "one or two neighbouring houses"
                    ),
                })

    for idx in range(interview.MAX_PORTRAIT_OPTIONS):
        entries.append({
            "key": f"portrait.window.{idx}",
            "channel": "portrait",
            "variant": "a",
            "answer_id": f"w{idx}",
            "distinguishes": (
                "one surviving time window from the others, by the placements "
                "returned in `distinguishing_placements`"
            ),
        })

    by_channel: dict[str, int] = {}
    for e in entries:
        by_channel[e["channel"]] = by_channel.get(e["channel"], 0) + 1

    return {
        "_README": (
            "Every copy key the interview engine can emit. The web client "
            "auto-skips a question whose keys have no authored copy, so any "
            "channel missing here is a channel the live interview cannot use. "
            "Generated by benchmarks/build_copy_manifest.py."
        ),
        "locales": list(LOCALES),
        "total_keys": len(entries),
        "keys_by_channel": by_channel,
        "entries": entries,
    }


def draft_for(entry: dict) -> dict[str, str]:
    ch, aid = entry["channel"], entry["answer_id"]
    variant_note = " (second phrasing)" if entry["variant"] == "b" else ""
    if ch == "element":
        return {loc: ELEMENT_DRAFT[aid][loc] + variant_note for loc in LOCALES}
    if ch == "modality":
        return {loc: MODALITY_DRAFT[aid][loc] + variant_note for loc in LOCALES}
    if ch == "sign_portrait":
        en, ru, uk, de = SIGN_PORTRAIT_DRAFT[aid]
        return {"en": en + variant_note, "ru": ru + variant_note,
                "uk": uk + variant_note, "de": de + variant_note}
    if ch == "decan":
        sign, decan = aid.rsplit("_", 1)
        en = (f"{SIGN_PORTRAIT_DRAFT[sign][0]} — and more so than the rest of "
              f"{sign}." if decan == "second"
              else f"{SIGN_PORTRAIT_DRAFT[sign][0]} — {DECAN_ORDINAL[decan]}.")
        return {"en": en, "ru": "", "uk": "", "de": ""}
    if ch == "mover_house":
        planet = entry["key"].split(".")[1]
        house = int(aid)
        area, detail = HOUSE_MEANING[house]
        if entry["variant"] == "a":
            en = f"Your {PLANET_MEANING[planet]} plays out in {area} — {detail}."
        else:
            en = (f"A time in your life when {PLANET_MEANING[planet]} showed up "
                  f"through {area}.")
        return {"en": en, "ru": "", "uk": "", "de": ""}
    return {"en": "", "ru": "", "uk": "", "de": ""}


def main() -> None:
    manifest = build_manifest()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows = []
    for e in manifest["entries"]:
        d = draft_for(e)
        translated = all(d[loc] for loc in LOCALES)
        rows.append({**e, "drafts": d,
                     "status": "draft" if translated else "draft_en_only"})

    lines = [
        "# Interview copy drafts",
        "",
        "**Owner action: correct the Russian atoms below.** Nothing here is",
        "authored by a person yet.",
        "",
        "Why this file exists: the web client auto-skips any question whose",
        "keys have no authored copy. Today the decan and mover-house channels",
        "have none, so a live interview ends at the sign and the engine never",
        "gets to ask the questions that actually narrow the time.",
        "",
        "**v3.2 changed the shape of this file.** It used to carry 315",
        "template-generated English sentences - one per planet x house x",
        "facet - which is 315 things to correct when there are only 22 ideas",
        "underneath them. Those ideas are now listed once each, in Russian, as",
        "**atoms**: twelve life spheres, ten planet themes, thirty-six decan",
        "traits, and the sentence templates that compose them into a question.",
        "Correct an atom once and every question built from it changes.",
        "",
        "**Russian is the master.** Translation to EN / DE / UK happens in a",
        "later task and only from rows the owner has approved. The web imports",
        "`approved` rows only - change `draft_ru` or `draft` to `approved`.",
        "",
        f"Generated by `benchmarks/build_copy_manifest.py`. The full key list",
        f"({manifest['total_keys']} keys) stays in",
        "`astro_engine/data/copy_manifest.json`; this file is the text behind",
        "it.",
        "",
        "## Coverage",
        "",
        "| Block | Rows | Locales | Composes |",
        "|---|---|---|---|",
        f"| Stage 1 and portraits | {len([r for r in rows if r['status'] == 'draft'])} | en, ru, uk, de | element, modality, sign_portrait keys directly |",
        f"| Life spheres (houses) | 12 | ru | the {manifest['keys_by_channel']['mover_house']} mover-house keys |",
        "| Planet themes | 10 | ru | the same mover-house keys |",
        f"| Decan traits | 36 | ru | the {manifest['keys_by_channel']['decan']} decan keys |",
        "| Sentence templates | 4 | ru | how the atoms become a question |",
        "",
        "## 1. Stage 1 and portraits — drafted in four locales",
        "",
        "| Key | Distinguishes | en | ru | uk | de | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["status"] != "draft":
            continue
        d = r["drafts"]
        lines.append(
            f"| `{r['key']}` | {r['distinguishes']} | {d['en']} | {d['ru']} | "
            f"{d['uk']} | {d['de']} | {r['status']} |"
        )

    lines += [
        "",
        "## 2. Life spheres — one line per house",
        "",
        "Used for every `planet.*.house.N.*` key. House N always means the same",
        "sphere; only the planet theme changes.",
        "",
        "| House | ru | Status |",
        "|---|---|---|",
    ]
    for h in range(1, 13):
        lines.append(f"| {h} | {HOUSE_ATOM_RU[h]} | draft_ru |")

    lines += [
        "",
        "## 3. Planet themes — one line per planet",
        "",
        "| Planet | ru | Status |",
        "|---|---|---|",
    ]
    for planet, _ in core.PLANETS:
        lines.append(f"| {planet} | {PLANET_ATOM_RU[planet]} | draft_ru |")

    lines += [
        "",
        "## 4. Decan traits — one line per sign and third",
        "",
        "Appearance and bearing, used for every `decan.<sign>.<third>.*` key.",
        "",
        "| Sign | Third | ru | Status |",
        "|---|---|---|---|",
    ]
    for sign in interview.TRAIT_SIGNS:
        for decan in interview.DECAN_NAMES:
            lines.append(
                f"| {sign} | {decan} | {DECAN_ATOM_RU[(sign, decan)]} | draft_ru |"
            )

    lines += [
        "",
        "## 5. Sentence templates",
        "",
        "The engine never sends prose; the client composes these from the atoms",
        "above. Square brackets are slots.",
        "",
        "| Template | ru | Status |",
        "|---|---|---|",
    ]
    for key, text in TEMPLATE_RU.items():
        lines.append(f"| `{key}` | {text} | draft_ru |")
    lines.append("")

    DRAFTS.parent.mkdir(parents=True, exist_ok=True)
    DRAFTS.write_text("\n".join(lines), encoding="utf-8")

    print(f"keys: {manifest['total_keys']}")
    for ch, n in sorted(manifest["keys_by_channel"].items()):
        print(f"  {ch:16} {n}")
    print(f"four-locale rows: {sum(1 for r in rows if r['status'] == 'draft')}")
    print(f"russian atoms: {12 + 10 + 36 + len(TEMPLATE_RU)}")
    print(f"wrote {MANIFEST}\nwrote {DRAFTS}")


if __name__ == "__main__":
    main()
