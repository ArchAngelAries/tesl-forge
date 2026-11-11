"""Card catalog in the game's original card JSON form (one CardSet per line, data/original-rules)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from .game import GameInstall

ATTRS = ("ManaCost", "Attack", "MaxHealth")


_SETS: dict = {}


def load_sets(game: GameInstall, path: str | None = None) -> list[dict]:
    """The original card sets (cached per file and modification time; callers copy before changing a card)."""
    source = path or game.original_rules
    if not source or not Path(source).is_file():
        raise FileNotFoundError("Original card data not found (data/original-rules/card-rule-graphs.jsonl.gz).")
    key = (str(source), Path(source).stat().st_mtime)
    if key not in _SETS:
        with gzip.open(source, "rt", encoding="utf-8") as f:
            _SETS.clear()
            _SETS[key] = [json.loads(line) for line in f if line.strip()]
    return _SETS[key]


def summarize(card: dict, set_name: str) -> dict:
    attrs = {a.get("Name"): a.get("Value") for a in card.get("EntityAttributes") or [] if a.get("Name") in ATTRS}
    rules = bool(card.get("TriggeredEffects") or card.get("Auras") or card.get("ActionPlayInformation")
                 or (card.get("ActivatedAbility") or {}).get("AbilityGroups"))
    return {"id": card["ResourceId"]["Id"], "name": card.get("Name"), "set": set_name, "type": card.get("Definition"),
            "rarity": card.get("Rarity"), "cost": attrs.get("ManaCost"), "attack": attrs.get("Attack"),
            "health": attrs.get("MaxHealth"), "subtypes": card.get("Subtypes"), "collectible": bool(card.get("Production") and card.get("ExportCode")),
            "image": card.get("Image"), "text": card.get("Description"), "has_rules": rules,
            "alternate_of": (card.get("AlternateOfCard") or {}).get("resourceId") or 0}


def catalog(game: GameInstall, path: str | None = None) -> list[dict]:
    out = []
    for s in load_sets(game, path):
        for c in s.get("Cards") or []:
            if c and c.get("ResourceId"):
                out.append(summarize(c, s.get("Name")))
    return out


def art_asset_paths(image: str) -> list[str]:
    """Card.Image ('ContentPack000/Cards/Visuals/x/x') -> bundle asset paths to try."""
    base = "assets/" + image.lower()
    return [base + ext for ext in (".png", ".tga", ".jpg", ".psd")]
