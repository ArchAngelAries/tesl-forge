"""No-code rule editor: card rules built from building blocks the game already runs.

A card's rules are original rule graphs (triggered effects such as Summon or Last Gasp, the play effect of an action or
item, auras, activated abilities) plus keyword attributes. The editor composes a new card from
  - keywords (on/off attributes: Guard, Charge, Lethal, Ward, Drain, ...; Rally N), and
  - any number of abilities taken from existing cards, each with its parameters editable: amounts (damage, healing, tokens,
    stat changes, thresholds) and card references (the card it summons, transforms into, ...).
Abilities are copied whole from cards the offline engine runs natively, so the result plays without new code; only the
parameters change. A truly new mechanic (one no card has) needs engine work and is reported as such.
"""
from __future__ import annotations

import copy
import re

KEYWORDS = [  # (label, attribute, kind)
    ("Guard", "Taunt", "bool"), ("Charge", "Charge", "bool"), ("Lethal", "Deathtouch", "bool"), ("Ward", "Ward", "bool"),
    ("Breakthrough", "Breakthrough", "bool"), ("Drain", "Drain", "bool"), ("Regenerate", "Regenerate", "bool"), ("Cover", "Cover", "bool"),
    ("Prophecy", "Prophecy", "bool"), ("Rally", "Rally", "int"), ("Immune to Silence", "ImmuneToSilence", "bool"),
    ("Can't attack", "CannotAttack", "bool"), ("Attacks either lane", "CanAttackOtherLane", "bool"),
]
KEYWORD_TEXT = {"Taunt": "Guard", "Deathtouch": "Lethal"}
ABILITY_FIELDS = {"triggered": "TriggeredEffects", "play": "ActionPlayInformation", "aura": "Auras"}
TRIGGER_LABEL = {"Summon": "Summon", "LastGasp": "Last Gasp", "Deathrattle": "Last Gasp", "WhenCardPreparesAttack": "When it attacks",
                 "Slay": "Slay", "Pilfer": "Pilfer", "WhenPlayerTurnStarts": "Start of your turn", "WhenPlayerTurnEnds": "End of your turn"}
VALUE_LABEL = {"HealthLoss": "Damage", "HealthGain": "Healing", "NumTokens": "How many", "NumCards": "How many cards", "Value": "Amount"}


def _walk(o, path, out, attr_name=None):
    if isinstance(o, dict):
        if o.get("ValueMethod") == "Constant" and isinstance(o.get("ConstantValue"), (int, float)) and o.get("ConstantValue"):
            if not any("Weight" in str(p) for p in path):
                label = VALUE_LABEL.get(str(path[-1]), str(path[-1])) if path else "Amount"
                out.append({"path": path + ["ConstantValue"], "value": o["ConstantValue"], "label": label, "type": "number"})
        if "AttributeModifications" in o and isinstance(o["AttributeModifications"], list):
            for i, m in enumerate(o["AttributeModifications"]):
                if isinstance(m, dict) and isinstance(m.get("Value"), (int, float)) and not isinstance(m.get("Value"), bool):
                    out.append({"path": path + ["AttributeModifications", i, "Value"], "value": m["Value"],
                                "label": {"Attack": "Power change", "MaxHealth": "Health change"}.get(m.get("Attribute"), str(m.get("Attribute") or "Change")),
                                "type": "number"})
        if isinstance(o.get("CardIdReference"), int) and o["CardIdReference"] not in (0, -1):
            out.append({"path": path + ["CardIdReference"], "value": o["CardIdReference"], "label": "Card", "type": "card"})
        for k, v in o.items():
            if k in ("AttributeModifications",):
                continue
            _walk(v, path + [k], out)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk(v, path + [i], out)


def abilities_of(card: dict) -> list[dict]:
    """The card's abilities, each with an id ('triggered:0', 'play:0', 'aura:0', 'activated:0') and its parameters."""
    out = []
    for kind, field in ABILITY_FIELDS.items():
        for i, a in enumerate(card.get(field) or []):
            params = []
            _walk(a, [], params)
            trig = a.get("TriggerType") if kind == "triggered" else None
            out.append({"id": f"{kind}:{i}", "kind": kind, "trigger": trig,
                        "label": TRIGGER_LABEL.get(trig, trig) if trig else {"play": "When played", "aura": "Ongoing (aura)"}[kind],
                        "targeting": a.get("ClientTargetingType") or a.get("PlayTargetingType"), "params": params})
    act = card.get("ActivatedAbility") or {}
    for i, g in enumerate(act.get("AbilityGroups") or []):
        params = []
        _walk(g, [], params)
        out.append({"id": f"activated:{i}", "kind": "activated", "trigger": None, "label": "Activate", "targeting": act.get("TargetingType"), "params": params})
    return out


def keywords_of(card: dict) -> dict:
    attrs = {a.get("Name"): a.get("Value") for a in card.get("EntityAttributes") or []}
    return {label: attrs.get(attr) for label, attr, _ in KEYWORDS if attr in attrs}


def _set(o, path, value):
    for p in path[:-1]:
        o = o[p]
    o[path[-1]] = value


def _ability(donor: dict, ability_id: str) -> tuple[str, object]:
    kind, _, index = ability_id.partition(":")
    i = int(index or 0)
    if kind in ABILITY_FIELDS:
        items = donor.get(ABILITY_FIELDS[kind]) or []
        if i >= len(items):
            raise ValueError(f"{donor.get('Name')} has no ability {ability_id}")
        return kind, copy.deepcopy(items[i])
    if kind == "activated":
        groups = (donor.get("ActivatedAbility") or {}).get("AbilityGroups") or []
        if i >= len(groups):
            raise ValueError(f"{donor.get('Name')} has no ability {ability_id}")
        return kind, copy.deepcopy(groups[i])
    raise ValueError(f"Unknown ability kind '{kind}' (triggered, play, aura, activated)")


def _set_attr(card: dict, name: str, value) -> None:
    for a in card.setdefault("EntityAttributes", []):
        if a.get("Name") == name:
            a["Value"] = value
            return
    card["EntityAttributes"].append({"Value": value, "Name": name, "$type": "SPTESL.BoolAttribute" if isinstance(value, bool) else "SPTESL.IntAttribute"})


def _retext(text: str, changes: list[tuple], notes: list, label: str) -> str:
    """Rewrite a changed number in the text only when it appears there exactly once; otherwise leave the text and say so."""
    for old, new, what in changes:
        if old == new:
            continue
        pat = re.compile(r"(?<![\d\w/])" + re.escape(str(abs(old))) + r"(?![\d\w/])")
        if len(pat.findall(text)) == 1:
            text = pat.sub(str(abs(new)), text)
        else:
            notes.append(f"{label}: {what} changed {old} -> {new}; update the card text to match")
    return text


def compose(card: dict, abilities: list[dict], keywords: dict | None, find) -> dict:
    """Give `card` exactly the listed abilities (copied from donors, parameters changed) and keyword values.
    abilities: [{"card": donor ref, "ability": "triggered:0", "params": {"<path joined by .>": value}}]; find(ref) -> card dict.
    Returns {"text": suggested card text, "notes": [...]}."""
    notes, texts = [], []
    if abilities is not None:
        for field in ABILITY_FIELDS.values():
            card[field] = []
        card["ActivatedAbility"] = {"TargetingType": "NoTarget", "TargetSelectors": [], "AbilityGroups": []}
        fx, refs, first_act, first_play, mech = [], [], None, None, []
        for spec in abilities:
            donor = find(str(spec["card"]))
            kind, item = _ability(donor, spec["ability"])
            params = {".".join(map(str, p["path"])): p for p in abilities_of({ABILITY_FIELDS.get(kind, "x"): [item]} if kind != "activated"
                                                                               else {"ActivatedAbility": {"AbilityGroups": [item]}})[0]["params"]}
            changes = []
            for key, value in (spec.get("params") or {}).items():
                if key not in params:
                    raise ValueError(f"{donor.get('Name')} {spec['ability']}: no parameter {key}")
                p = params[key]
                new = int(value)
                _set(item, p["path"], new)
                if p["type"] == "number":
                    changes.append((p["value"], new, p["label"]))
            if kind == "activated":
                if first_act is None:
                    first_act = donor.get("ActivatedAbility") or {}
                    card["ActivatedAbility"]["TargetingType"] = first_act.get("TargetingType", "NoTarget")
                    card["ActivatedAbility"]["TargetSelectors"] = copy.deepcopy(first_act.get("TargetSelectors") or [])
                card["ActivatedAbility"]["AbilityGroups"].append(item)
            else:
                card[ABILITY_FIELDS[kind]].append(item)
                if kind == "play" and first_play is None:
                    first_play = donor
            fx += [r for r in donor.get("CardFxRelations") or [] if r not in fx]
            refs += [r for r in donor.get("CardReferences") or [] if r not in refs]
            mech += [m for m in donor.get("MechanicsEntries") or [] if m.get("MechanicType") not in [x.get("MechanicType") for x in mech]]
            t = re.sub(r"\s+", " ", donor.get("Description") or "").strip()
            if donor.get("Name") and card.get("Name"):
                t = t.replace(donor["Name"], card["Name"])      # "When Fiery Imp attacks" -> the new card's name
            t = _retext(t, changes, notes, donor.get("Name") or "ability")
            if t and t not in texts:
                texts.append(t)
        card["CardFxRelations"] = fx
        card["MechanicsEntries"] = copy.deepcopy(mech)     # tooltips of the abilities the card now has
        if refs:
            card["CardReferences"] = refs
        if first_play is not None and first_play.get("PlayRequirements"):
            card["PlayRequirements"] = copy.deepcopy(first_play["PlayRequirements"])
        if len(texts) > 1:
            notes.append("text combines the donor cards' texts; check it reads as one card")
    shown = []
    for label, attr, kind in KEYWORDS:
        if not keywords or label not in keywords:
            continue
        v = keywords[label]
        value = int(v or 0) if kind == "int" else bool(v)
        _set_attr(card, attr, value)
        if value:
            shown.append(f"{label} {value}" if kind == "int" else label)
    kw = ", ".join(f"<b><color=E9E0CD>{k}</color></b>" for k in shown)
    body = "<br>".join(texts)
    return {"text": (kw + ("<br>" if kw and body else "") + body) if (kw or body) else None, "notes": notes}
