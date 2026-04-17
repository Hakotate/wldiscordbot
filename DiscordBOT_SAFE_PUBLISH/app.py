import json
import math
import os
import re
import sys
from html import escape
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, render_template, request


APP_TITLE = "Warlords Lookup"
HYPIXEL_PLAYER_URL = "https://api.hypixel.net/v2/player"
MOJANG_PROFILE_URL = "https://api.mojang.com/users/profiles/minecraft/{username}"
UUID_PATTERN = re.compile(
    r"^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)
CLASS_ORDER = ("warrior", "paladin", "mage", "shaman")
CLASS_META = {
    "warrior": {"label": "Warrior", "theme": "warrior", "specs": ("berserker", "defender", "revenant")},
    "paladin": {"label": "Paladin", "theme": "paladin", "specs": ("avenger", "crusader", "protector")},
    "mage": {"label": "Mage", "theme": "mage", "specs": ("pyromancer", "cryomancer", "aquamancer")},
    "shaman": {"label": "Shaman", "theme": "shaman", "specs": ("thunderlord", "spiritguard", "earthwarden")},
}
SPEC_LABELS = {
    "berserker": "Berserker",
    "defender": "Defender",
    "revenant": "Revenant",
    "avenger": "Avenger",
    "crusader": "Crusader",
    "protector": "Protector",
    "cryomancer": "Cryomancer",
    "pyromancer": "Pyromancer",
    "aquamancer": "Aquamancer",
    "thunderlord": "Thunderlord",
    "spiritguard": "Spiritguard",
    "earthwarden": "Earthwarden",
}
WEAPON_MATERIAL_NAMES = {
    "WOODEN_AXE": "Steel Sword",
    "WOOD_AXE": "Steel Sword",
    "STONE_AXE": "Training Sword",
    "GOLDEN_HOE": "Hatchet",
    "GOLD_HOE": "Hatchet",
    "IRON_SHOVEL": "Hammer",
    "STONE_PICKAXE": "Walking Stick",
    "SALMON": "Scimitar",
    "ROTTEN_FLESH": "Pike",
    "MUTTON": "Claws",
    "PUMPKIN_PIE": "Orc Axe",
    "RABBIT_STEW": "Bludgeon",
    "IRON_AXE": "Demonblade",
    "GOLD_AXE": "Venomstrike",
    "DIAMOND_HOE": "Gem Axe",
    "GOLDEN_SHOVEL": "Stone Mallet",
    "GOLD_SHOVEL": "Stone Mallet",
    "IRON_PICKAXE": "World Tree Branch",
    "PUFFERFISH": "Golden Gladius",
    "POTATO": "Halberd",
    "PORKCHOP": "Mandibles",
    "COOKED_COD": "Doubleaxe",
    "DIAMOND_AXE": "Diamondspark",
    "WOODEN_HOE": "Zweireaper",
    "WOOD_HOE": "Zweireaper",
    "STONE_HOE": "Runeblade",
    "IRON_HOE": "Elven Greatsword",
    "WOODEN_SHOVEL": "Nomegusta",
    "WOOD_SHOVEL": "Nomegusta",
    "DIAMOND_SHOVEL": "Gemcrusher",
    "GOLDEN_PICKAXE": "Flameweaver",
    "GOLD_PICKAXE": "Flameweaver",
    "CLOWNFISH": "Magmasword",
    "MELON": "Divine Reach",
    "STRING": "Hammer of Light",
    "CHICKEN": "Nethersteel Katana",
    "BEEF": "Katar",
    "BREAD": "Runic Axe",
    "MUSHROOM_STEW": "Lunar Relic",
    "COOKED_CHICKEN": "Tenderizer",
    "RAW_CHICKEN": "Nethersteel Katana",
    "STONE_SPADE": "Drakefang",
    "STONE_SHOVEL": "Drakefang",
    "WOODEN_PICKAXE": "Abbadon",
    "WOOD_PICKAXE": "Abbadon",
    "DIAMOND_PICKAXE": "Void Twig",
    "COD": "Frostbite",
    "POISONOUS_POTATO": "Ruby Thorn",
    "APPLE": "Enderfist",
    "BAKED_POTATO": "Broccomace",
    "COOKED_SALMON": "Felflame Blade",
    "COOKED_MUTTON": "Amaranth",
    "COOKED_BEEF": "Armblade",
    "COOKED_PORKCHOP": "Gemini",
    "GOLDEN_CARROT": "Void Edge",
    "GOLD_CARROT": "Void Edge",
}
WEAPON_SPEC_LOOKUP = {
    0: {"class_key": "mage", "specs": {0: "pyromancer", 1: "cryomancer", 2: "aquamancer"}},
    1: {"class_key": "warrior", "specs": {0: "berserker", 1: "defender", 2: "revenant"}},
    2: {"class_key": "paladin", "specs": {0: "avenger", 1: "crusader", 2: "protector"}},
    3: {"class_key": "shaman", "specs": {0: "thunderlord", 1: "earthwarden", 2: "spiritguard"}},
}
MODE_META = (
    ("Capture the Flag", "capturetheflag"),
    ("Domination", "domination"),
    ("Team Deathmatch", "teamdeathmatch"),
)
AVERAGE_KDA = (3.85 + 2.67) / 2.0
GAMES_PLAYED_TO_RANK = 50
DISQUALIFY_MAX_WL = 5
DISQUALIFY_PERCENT_LEFT = 4
SPEC_AVERAGES = {
    "pyromancer": {"dhp": 109706, "wl": 1},
    "cryomancer": {"dhp": 103596, "wl": 1},
    "aquamancer": {"dhp": 131094, "wl": 1},
    "avenger": {"dhp": 113914, "wl": 1},
    "crusader": {"dhp": 114263, "wl": 1},
    "protector": {"dhp": 153370, "wl": 1},
    "thunderlord": {"dhp": 121714, "wl": 1},
    "spiritguard": {"dhp": 152469, "wl": 1},
    "earthwarden": {"dhp": 131804, "wl": 1},
    "berserker": {"dhp": 99964, "wl": 1},
    "defender": {"dhp": 98341, "wl": 1},
    "revenant": {"dhp": 150710, "wl": 1},
}
SPEC_BOOSTS = {
    "warrior": {
        "berserker": (("Blood Frenzy", "blood_frenzy"), ("Berserker's Fury", "berserkers_fury"), ("Mighty Fists", "mighty_fists"), ("Wounding Strike", "wounding_strike_berserker"), ("Seismic Shift", "seismic_shift")),
        "defender": (("Fervent Force", "fervent_force"), ("Heroic Intervention", "heroic_intervention"), ("Vitality Boost", "vitality_boost"), ("Wounding Strike", "wounding_strike_defender"), ("Solitary Resistance", "solitary_resistance")),
        "revenant": (("Orbs of Life", "orbs_of_life"), ("Reckless Ascent", "reckless_ascent"), ("One Man Army", "one_man_army"), ("Undying Steed", "undying_steed"), ("Healing Link", "healing_link")),
    },
    "paladin": {
        "avenger": (("Divine Vindication", "divine_vindication"), ("Arm Of The Almighty", "arm_of_the_almighty"), ("Greater Sacrality", "greater_sacrality"), ("Warding Wrath", "warding_wrath"), ("Zealous Mark", "zealous_mark")),
        "crusader": (("Blade Of Willpower", "blade_of_willpower"), ("Vigorous Infusion", "vigorous_infusion"), ("Seraphim Shield", "seraphim_shield"), ("Rallying Presence", "rallying_presence"), ("Sovereign Solitude", "sovereign_solitude")),
        "protector": (("Divine Effulgence", "divine_effulgence"), ("Lustrous Crown", "lustrous_crown"), ("Lightspeed Infusion", "lightspeed_infusion"), ("Piercing Radiance", "piercing_radiance"), ("Hammer Of Judgement", "hammer_of_judgement")),
    },
    "mage": {
        "cryomancer": (("Blizzard Breath", "blizzard_breath"), ("Frost Missile", "frost_missile"), ("Steadfast Warp", "steadfast_warp"), ("Arcane Recluse", "arcane_recluse"), ("Chilly Aura", "chilly_aura")),
        "pyromancer": (("Meteor", "meteor"), ("Arcane Shatter", "arcane_shatter"), ("Burst Chain", "burst_chain"), ("Dimensional Warp", "dimensional_warp"), ("Flame Breath", "flame_breath")),
        "aquamancer": (("Clairvoyance", "clairvoyance"), ("Divine Purification", "divine_purification"), ("Acid Rain", "acid_rain"), ("Typhoon Bolt", "typhoon_bolt"), ("Arcane Reflection", "arcane_reflection")),
    },
    "shaman": {
        "thunderlord": (("Galvanized Spark", "galvanized_spark"), ("Transistor", "transistor"), ("Electromagnetic Chains", "electromagnetic_chains"), ("Eye Of The Storm", "eye_of_the_storm"), ("Symphonic Windfury", "symphonic_windfury")),
        "spiritguard": (("Smothering Soulbind", "smothering_soulbind"), ("Devil's Debt", "devils_debt"), ("Wrath Of The Fallen", "wrath_of_the_fallen"), ("Spiritual Deflection", "spiritual_deflection"), ("Permeating Link", "permeating_link")),
        "earthwarden": (("Earthbound Infusion", "earthbound_infusion"), ("Megalithic Boulder", "megalithic_boulder"), ("Accelerated Spike", "accelerated_spike"), ("Augmented Chains", "augmented_chains"), ("Totemic Boon", "totemic_boon")),
    },
}
SKIP_EXACT = {
    "packages", "chosen_class", "coins", "magic_dust", "void_shards", "current_weapon", "selected_mount",
    "wins", "losses", "kills", "deaths", "assists", "damage", "heal", "damage_prevented", "life_leeched",
    "mvp_count", "win_streak", "total_domination_score",
    "dom_point_captures", "dom_point_defends",
    "flag_conquer_self", "flag_returns"
}
SKIP_SUBSTRINGS = ("legacyachievement", "_selection", "hotkey", "autostrike", "hide_prestige", "packages", "hints")
OTHER_FIELD_SKIP_EXACT = {"damage_taken", "penalty", "wins_blu", "wins_red"}
OTHER_FIELD_CANONICAL_KEYS = {
    "afk_warning": "penalty",
    "afk_warnings": "penalty",
}
LABEL_OVERRIDES = {
    "play_streak": "Play Streak",
    "powerups_collected": "Powerups Collected",
    "energypowerups": "Energy Powerups",
    "wins_blu": "Blue Team Wins",
    "wins_red": "Red Team Wins",
    "penalty": "AFK Warnings / Penalties",
    "broken_inventory": "Broken Weapons",
    "flag_conquer_team": "Flag Captured By The Team",
    "legendary_broken_inventory": "Broken Legendary Weapons",
}

def resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def load_env_file(path: str = ".env") -> None:
    resolved_path = resource_path(path)
    if not os.path.exists(resolved_path):
        return
    with open(resolved_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            normalized_key = key.strip().lstrip("\ufeff")
            os.environ[normalized_key] = value.strip().strip('"').strip("'")


load_env_file()
app = Flask(__name__, template_folder=resource_path("templates"))


def http_get_json(url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    merged = {"User-Agent": "WarlordsLookup/1.0"}
    if headers:
        merged.update(headers)
    with urlopen(Request(url, headers=merged), timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_uuid_for_username(username: str) -> str:
    try:
        payload = http_get_json(MOJANG_PROFILE_URL.format(username=username))
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError(f"Minecraft username '{username}' was not found.") from exc
        raise ValueError(f"Mojang lookup failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise ValueError(f"Could not reach Mojang to resolve '{username}'.") from exc
    player_uuid = payload.get("id")
    if not player_uuid:
        raise ValueError(f"Minecraft username '{username}' was not found.")
    return player_uuid


def normalize_player_uuid(player_uuid: str) -> str:
    normalized = str(player_uuid or "").strip().lower().replace("-", "")
    if not re.fullmatch(r"[0-9a-f]{32}", normalized):
        raise ValueError("Please provide a valid Minecraft UUID.")
    return normalized


def fetch_hypixel_player(uuid: str) -> Dict[str, Any]:
    load_env_file()
    api_key = os.environ.get("HYPIXEL_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing HYPIXEL_API_KEY in .env.")
    try:
        payload = http_get_json(f"{HYPIXEL_PLAYER_URL}?{urlencode({'uuid': uuid})}", {"API-Key": api_key})
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        if exc.code == 403 and "1006" in body:
            raise ValueError("Hypixel/Cloudflare is blocking this IP with error 1006. Try another network or a new public IP.") from exc
        if exc.code == 403:
            raise ValueError(f"Hypixel returned HTTP 403. Response body: {body or 'empty response'}") from exc
        if exc.code == 429:
            raise ValueError("Hypixel rate-limited the request. Wait a moment and try again.") from exc
        raise ValueError(f"Hypixel request failed with HTTP {exc.code}. Response body: {body or 'empty response'}") from exc
    except URLError as exc:
        raise ValueError("Could not reach the Hypixel API.") from exc
    if not payload.get("success"):
        raise ValueError(payload.get("cause") or "Hypixel returned an unsuccessful response.")
    player = payload.get("player")
    if not player:
        raise ValueError("No Hypixel player data was returned for that username.")
    return player


def safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        try:
            return int(text)
        except ValueError:
            try:
                return int(float(text))
            except ValueError:
                return 0
    return 0


def format_number(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if value in (None, ""):
        return "0"
    return str(value)


def ratio(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00"
    return f"{numerator / denominator:.2f}"


def percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def row(label: str, value: str, tone: str = "tone-white") -> Dict[str, str]:
    return {"label": label, "value": value, "tone": tone}


def labelize(key: str) -> str:
    override = LABEL_OVERRIDES.get(str(key or "").strip().lower())
    if override:
        return override
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key or "").replace("-", "_"))
    return " ".join(part.capitalize() for part in normalized.split("_") if part)


def prettify_identifier(value: Any) -> str:
    if value in (None, ""):
        return "0"
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value).replace("-", "_"))
    return " ".join(part.capitalize() for part in normalized.split("_") if part)


def resolve_weapon_name(material: Any) -> str:
    material_key = str(material or "").upper()
    return WEAPON_MATERIAL_NAMES.get(material_key, prettify_identifier(material_key))


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


WEAPON_SCORE_PROFILES = {
    "COMMON": (
        ("damage", 90.0, 100.0),
        ("chance", 10.0, 18.0),
        ("multiplier", 150.0, 170.0),
        ("health", 180.0, 220.0),
    ),
    "RARE": (
        ("damage", 95.0, 105.0),
        ("chance", 10.0, 18.0),
        ("multiplier", 150.0, 170.0),
        ("health", 180.0, 220.0),
        ("energy", 5.0, 15.0),
    ),
    "EPIC": (
        ("damage", 100.0, 110.0),
        ("chance", 15.0, 20.0),
        ("multiplier", 160.0, 190.0),
        ("health", 220.0, 275.0),
        ("energy", 15.0, 20.0),
        ("cooldown", 3.0, 5.0),
    ),
    "LEGENDARY": (
        ("damage", 110.0, 120.0),
        ("chance", 15.0, 25.0),
        ("multiplier", 180.0, 200.0),
        ("health", 250.0, 400.0),
        ("energy", 20.0, 25.0),
        ("cooldown", 5.0, 10.0),
        ("movement", 5.0, 10.0),
    ),
}


def weapon_score_percent(weapon: Dict[str, Any]) -> float:
    profile = WEAPON_SCORE_PROFILES.get(str(weapon.get("category") or "").upper())
    if not profile:
        return 0.0
    stat_rolls = [
        clamp((float(weapon.get(stat_name) or 0) - minimum) / (maximum - minimum), 0.0, 1.0)
        for stat_name, minimum, maximum in profile
    ]
    return (sum(stat_rolls) / len(stat_rolls)) * 100.0


def format_weapon_score(weapon: Dict[str, Any]) -> str:
    score = round(weapon_score_percent(weapon), 1)
    if score.is_integer():
        return f"{int(score)}%"
    return f"{score:.1f}%"


def resolve_weapon_full_title(weapon: Dict[str, Any], spec_label_override: Optional[str] = None) -> str:
    spec_info = resolve_weapon_spec(weapon.get("spec"))
    spec_label = spec_label_override or spec_info["spec_label"]
    base_name = resolve_weapon_name(weapon.get("material"))
    return f"{base_name} Of The {spec_label}"


def weapon_rarity_tone(category: Any) -> str:
    category_key = str(category or "").upper()
    if category_key == "LEGENDARY":
        return "tone-warn"
    if category_key == "EPIC":
        return "tone-pink"
    if category_key == "RARE":
        return "tone-blue"
    if category_key == "COMMON":
        return "tone-white"
    return "tone-cyan"


def forged_value(value: Any, upgrade_times: int, per_upgrade: float) -> int:
    return math.ceil(float(value or 0) * (1 + per_upgrade * upgrade_times))


def forged_damage_range(value: Any, upgrade_times: int) -> str:
    forged_damage = forged_value(value, upgrade_times, 0.075)
    minimum = math.floor(forged_damage * 0.85)
    maximum = math.floor(forged_damage * 1.15)
    return f"{minimum:,} - {maximum:,}"


def resolve_weapon_spec(spec_data: Any) -> Dict[str, str]:
    if not isinstance(spec_data, dict):
        return {"class_key": "", "class_label": "Unknown", "spec_label": "Unknown"}
    class_info = WEAPON_SPEC_LOOKUP.get(safe_int(spec_data.get("playerClass")))
    if not class_info:
        return {"class_key": "", "class_label": "Unknown", "spec_label": "Unknown"}
    class_key = class_info["class_key"]
    spec_key = class_info["specs"].get(safe_int(spec_data.get("spec")))
    return {
        "class_key": class_key,
        "class_label": CLASS_META[class_key]["label"],
        "spec_label": SPEC_LABELS.get(spec_key or "", "Unknown"),
    }


def spec_key_from_label(spec_label: Optional[str]) -> Optional[str]:
    if not spec_label:
        return None
    normalized = str(spec_label).strip().lower()
    for key, label in SPEC_LABELS.items():
        if label.lower() == normalized:
            return key
    return normalized if normalized in SPEC_LABELS else None


def weapon_spec_key(weapon: Dict[str, Any]) -> Optional[str]:
    if not isinstance(weapon, dict):
        return None
    spec_data = weapon.get("spec")
    if not isinstance(spec_data, dict):
        return None
    class_info = WEAPON_SPEC_LOOKUP.get(safe_int(spec_data.get("playerClass")))
    if not class_info:
        return None
    return class_info["specs"].get(safe_int(spec_data.get("spec")))


def weapon_lookup(weapons: Any) -> Dict[int, Dict[str, Any]]:
    if not isinstance(weapons, list):
        return {}
    return {
        safe_int(weapon.get("id")): weapon
        for weapon in weapons
        if isinstance(weapon, dict) and safe_int(weapon.get("id")) > 0
    }


def looks_like_weapon_record(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    required = {"id", "material", "category", "spec"}
    if not required.issubset(value.keys()):
        return False
    return safe_int(value.get("id")) > 0


def collect_weapon_records(value: Any, bucket: Dict[int, Dict[str, Any]]) -> None:
    if looks_like_weapon_record(value):
        weapon_id = safe_int(value.get("id"))
        bucket.setdefault(weapon_id, value)
    if isinstance(value, dict):
        for child in value.values():
            collect_weapon_records(child, bucket)
    elif isinstance(value, list):
        for child in value:
            collect_weapon_records(child, bucket)


def weapon_lookup_from_warlords(warlords: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    inventory = weapon_lookup(warlords.get("weapon_inventory"))
    collect_weapon_records(warlords, inventory)
    return inventory


def resolve_weapon_record(weapon_id: Any, inventory: Dict[int, Dict[str, Any]], spec_label_override: Optional[str] = None) -> Optional[Dict[str, Any]]:
    expected_spec_key = spec_key_from_label(spec_label_override)
    resolved_id = safe_int(weapon_id)
    weapon = inventory.get(resolved_id)
    if weapon and (not expected_spec_key or weapon_spec_key(weapon) == expected_spec_key):
        return weapon

    if not expected_spec_key:
        return weapon

    candidates = [item for item in inventory.values() if weapon_spec_key(item) == expected_spec_key]
    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            1 if item.get("unlocked") else 0,
            1 if item.get("playStreak") else 0,
            1 if item.get("crafted") else 0,
            safe_int(item.get("upgradeTimes")),
            safe_int(item.get("id")),
        ),
        reverse=True,
    )
    return candidates[0]


def resolve_weapon_id_for_display(weapon_id: Any, inventory: Dict[int, Dict[str, Any]], spec_label_override: Optional[str] = None) -> Optional[int]:
    weapon = resolve_weapon_record(weapon_id, inventory, spec_label_override)
    if not weapon:
        return None
    return safe_int(weapon.get("id"))


def build_weapon_card(section_label: str, weapon_id: Any, inventory: Dict[int, Dict[str, Any]], spec_label_override: Optional[str] = None) -> Dict[str, Any]:
    weapon = resolve_weapon_record(weapon_id, inventory, spec_label_override)
    if not weapon:
        return {
            "label": section_label,
            "title": f"Unknown Weapon ({format_number(weapon_id)})",
            "subtitle": "Could not match this ID in weapon_inventory",
            "tone": "tone-bad",
            "rows": [row("Weapon ID", format_number(weapon_id), "tone-white")],
        }

    spec_info = resolve_weapon_spec(weapon.get("spec"))
    detail_line = f"{prettify_identifier(weapon.get('category'))} | {spec_info['class_label']}"
    upgrade_max = safe_int(weapon.get("upgradeMax"))
    upgrade_times = safe_int(weapon.get("upgradeTimes"))
    upgrade_line = f"{upgrade_times}/{upgrade_max}" if upgrade_max > 0 else format_number(upgrade_times)
    damage_value = forged_damage_range(weapon.get("damage"), upgrade_times)
    crit_chance = f"{format_number(weapon.get('chance'))}%"
    crit_multiplier = f"{format_number(weapon.get('multiplier'))}%"
    health_value = f"+{forged_value(weapon.get('health'), upgrade_times, 0.25):,}"
    energy_value = f"+{forged_value(weapon.get('energy'), upgrade_times, 0.10):,}"
    cooldown_value = f"+{forged_value(weapon.get('cooldown'), upgrade_times, 0.075):,}%"
    speed_value = f"+{forged_value(weapon.get('movement'), upgrade_times, 0.075):,}%"
    weapon_score_value = format_weapon_score(weapon)
    crafted_value = "Crafted" if weapon.get("crafted") else "Uncrafted"
    void_forged_value = f"[{upgrade_line}]"
    return {
        "label": section_label,
        "title": resolve_weapon_full_title(weapon),
        "subtitle": detail_line,
        "tone": weapon_rarity_tone(weapon.get("category")),
        "class_label": spec_info["class_label"],
        "class_theme": spec_info["class_key"],
        "spec_key": weapon_spec_key(weapon),
        "spec_label": spec_label_override or spec_info["spec_label"],
        "rows": [
            row("Weapon Score (Approximately)", weapon_score_value, "tone-cyan"),
            row("Damage", damage_value, "tone-bad"),
            row("Crit Chance", crit_chance, "tone-bad"),
            row("Crit Multiplier", crit_multiplier, "tone-bad"),
            row("Health", health_value, "tone-good"),
            row("Max Energy", energy_value, "tone-good"),
            row("Cooldown Reduction", cooldown_value, "tone-good"),
            row("Speed", speed_value, "tone-good"),
            row("Crafted", crafted_value, "tone-cyan" if weapon.get("crafted") else "tone-white"),
            row("Void Forged", void_forged_value, "tone-pink"),
        ],
    }


def resolve_weapon_title_by_id(weapon_id: Any, inventory: Dict[int, Dict[str, Any]], spec_label_override: Optional[str] = None) -> str:
    weapon = resolve_weapon_record(weapon_id, inventory, spec_label_override)
    if not weapon:
        return "Unavailable"
    return resolve_weapon_full_title(weapon, spec_label_override)


def resolve_weapon_tone_by_id(weapon_id: Any, inventory: Dict[int, Dict[str, Any]], spec_label_override: Optional[str] = None) -> str:
    weapon = resolve_weapon_record(weapon_id, inventory, spec_label_override)
    if not weapon:
        return "tone-white"
    return weapon_rarity_tone(weapon.get("category"))


def build_resolved_weapon_cards(warlords: Dict[str, Any]) -> List[Dict[str, Any]]:
    inventory = weapon_lookup_from_warlords(warlords)
    if not inventory:
        return []

    ordered_ids: List[int] = []
    labels_by_id: Dict[int, List[str]] = {}

    def add_weapon_label(label: str, weapon_id: Any) -> None:
        resolved_id = resolve_weapon_id_for_display(weapon_id, inventory, label.replace("Bound / ", "") if label.startswith("Bound / ") else None)
        if resolved_id is None and label == "Current Weapon":
            resolved_id = safe_int(weapon_id)
        if resolved_id is None or resolved_id <= 0:
            return
        if resolved_id not in labels_by_id:
            labels_by_id[resolved_id] = []
            ordered_ids.append(resolved_id)
        if label not in labels_by_id[resolved_id]:
            labels_by_id[resolved_id].append(label)

    add_weapon_label("Current Weapon", warlords.get("current_weapon"))
    bound_weapons = warlords.get("bound_weapon")
    if isinstance(bound_weapons, dict):
        for class_key in CLASS_ORDER:
            class_bindings = bound_weapons.get(class_key)
            if not isinstance(class_bindings, dict):
                continue
            for spec_key in CLASS_META[class_key]["specs"]:
                if spec_key in class_bindings:
                    add_weapon_label(f"Bound / {SPEC_LABELS[spec_key]}", class_bindings.get(spec_key))

    cards: List[Dict[str, Any]] = []
    for weapon_id in ordered_ids:
        joined_label = " | ".join(labels_by_id[weapon_id])
        spec_override = None
        if joined_label.startswith("Bound / ") and " | " not in joined_label:
            spec_override = joined_label.replace("Bound / ", "")
        card = build_weapon_card(joined_label, weapon_id, inventory, spec_override)
        cards.append(card)
    return cards


def group_weapon_cards(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for card in cards:
        class_label = str(card.get("class_label") or "Other")
        grouped.setdefault(class_label, []).append(card)
    ordered_groups: List[Dict[str, Any]] = []
    preferred_order = [CLASS_META[class_key]["label"] for class_key in CLASS_ORDER]
    for class_label in preferred_order + [label for label in grouped if label not in preferred_order]:
        if class_label in grouped:
            grouped[class_label].sort(
                key=lambda card: (
                    CLASS_META.get(str(card.get("class_theme") or ""), {}).get("specs", ()).index(card.get("spec_key"))
                    if card.get("spec_key") in CLASS_META.get(str(card.get("class_theme") or ""), {}).get("specs", ())
                    else 999,
                    str(card.get("title") or ""),
                )
            )
            theme = str(grouped[class_label][0].get("class_theme") or "")
            ordered_groups.append({"label": class_label, "theme": theme, "cards": grouped[class_label]})
    return ordered_groups


def build_bound_weapon_rows(warlords: Dict[str, Any], inventory: Dict[int, Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    bound_weapons = warlords.get("bound_weapon")
    if not isinstance(bound_weapons, dict):
        return rows
    for class_key in CLASS_ORDER:
        class_bindings = bound_weapons.get(class_key)
        if not isinstance(class_bindings, dict):
            continue
        for spec_key in CLASS_META[class_key]["specs"]:
            if spec_key in class_bindings:
                weapon_id = class_bindings.get(spec_key)
                resolved_title = resolve_weapon_title_by_id(weapon_id, inventory, SPEC_LABELS[spec_key])
                if resolved_title == "Unavailable":
                    continue
                rows.append(row(SPEC_LABELS[spec_key], resolved_title, resolve_weapon_tone_by_id(weapon_id, inventory, SPEC_LABELS[spec_key])))
    return rows


def get_rank_label(player: Dict[str, Any]) -> str:
    if player.get("prefix"):
        return str(player["prefix"])
    if str(player.get("monthlyPackageRank") or "").upper() == "SUPERSTAR":
        return "[MVP++]"
    if str(player.get("newPackageRank") or "").upper() == "MVP_PLUS":
        return "[MVP+]"
    if str(player.get("newPackageRank") or "").upper() == "MVP":
        return "[MVP]"
    if str(player.get("newPackageRank") or "").upper() == "VIP_PLUS":
        return "[VIP+]"
    if str(player.get("newPackageRank") or "").upper() == "VIP":
        return "[VIP]"
    return "[DEFAULT]"


MINECRAFT_COLOR_MAP = {
    "BLACK": "#000000",
    "DARK_BLUE": "#0000AA",
    "DARK_GREEN": "#00AA00",
    "DARK_AQUA": "#00AAAA",
    "DARK_RED": "#AA0000",
    "DARK_PURPLE": "#AA00AA",
    "GOLD": "#FFAA00",
    "GRAY": "#AAAAAA",
    "DARK_GRAY": "#555555",
    "BLUE": "#5555FF",
    "GREEN": "#55FF55",
    "AQUA": "#55FFFF",
    "RED": "#FF5555",
    "LIGHT_PURPLE": "#FF55FF",
    "YELLOW": "#FFFF55",
    "WHITE": "#FFFFFF",
}


def hypixel_color_hex(color_name: Any, default: str) -> str:
    return MINECRAFT_COLOR_MAP.get(str(color_name or "").upper(), default)


def get_rank_segments(player: Dict[str, Any]) -> List[Dict[str, str]]:
    rank_label = get_rank_label(player)
    if player.get("prefix"):
        return [{"text": rank_label, "color": hypixel_color_hex(player.get("monthlyRankColor"), "#FFAA00")}]

    monthly_rank = str(player.get("monthlyPackageRank") or "").upper()
    package_rank = str(player.get("newPackageRank") or "").upper()
    plus_color = hypixel_color_hex(player.get("rankPlusColor"), "#FF5555")

    if monthly_rank == "SUPERSTAR":
        base_color = hypixel_color_hex(player.get("monthlyRankColor"), "#FFAA00")
        return [
            {"text": "[MVP", "color": base_color},
            {"text": "++", "color": plus_color},
            {"text": "]", "color": base_color},
        ]
    if package_rank == "MVP_PLUS":
        return [
            {"text": "[MVP", "color": "#55FFFF"},
            {"text": "+", "color": plus_color},
            {"text": "]", "color": "#55FFFF"},
        ]
    if package_rank == "MVP":
        return [{"text": "[MVP]", "color": "#55FFFF"}]
    if package_rank == "VIP_PLUS":
        return [
            {"text": "[VIP", "color": "#55FF55"},
            {"text": "+", "color": "#FFAA00"},
            {"text": "]", "color": "#55FF55"},
        ]
    if package_rank == "VIP":
        return [{"text": "[VIP]", "color": "#55FF55"}]
    return [{"text": rank_label, "color": "#F5F8FF"}]


def level_tone(value: int, maximum: int) -> str:
    return "tone-good" if value >= maximum else "tone-bad"


def class_level(warlords: Dict[str, Any], class_name: str) -> int:
    keys = [f"{class_name}_skill{i}" for i in range(1, 6)] + [
        f"{class_name}_cooldown", f"{class_name}_critchance", f"{class_name}_critmultiplier",
        f"{class_name}_energy", f"{class_name}_health"
    ]
    return sum(safe_int(warlords.get(key)) for key in keys)


def null_zero(value: Optional[int]) -> int:
    return int(value or 0)


def rounded_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 2)


def calculate_dhp(warlords: Dict[str, Any], prefix: str, plays: int) -> int:
    damage = safe_int(warlords.get(f"damage_{prefix}"))
    heal = safe_int(warlords.get(f"heal_{prefix}"))
    prevented = safe_int(warlords.get(f"damage_prevented_{prefix}"))
    if plays <= 0:
        return 0
    return round((damage + heal + prevented) / plays)


def adjust_average(value: float, average: float) -> float:
    if average <= 0:
        return 0.0
    ratio_value = value / average
    if ratio_value >= 5:
        return 1.0
    if ratio_value <= 0:
        return 0.0
    return 1.00699 + (-1.02107 / (1.01398 + pow(ratio_value, 3.09248)))


def calculate_spec_sr(warlords: Dict[str, Any], spec_name: str, total_kda: float, total_plays: int) -> Optional[int]:
    spec_plays = safe_int(warlords.get(f"{spec_name}_plays"))
    spec_wins = safe_int(warlords.get(f"wins_{spec_name}"))
    spec_losses = derived_spec_losses(warlords, spec_name)
    spec_wl = rounded_ratio(spec_wins, spec_losses if spec_losses > 0 else 1)
    spec_dhp = calculate_dhp(warlords, spec_name, spec_plays)
    penalty = safe_int(warlords.get("penalty"))

    if spec_plays < GAMES_PLAYED_TO_RANK:
        return None
    if spec_wl > DISQUALIFY_MAX_WL:
        return None
    if total_plays > 0 and (penalty / total_plays) * 100 >= DISQUALIFY_PERCENT_LEFT:
        return None

    averages = SPEC_AVERAGES[spec_name]
    sr_from_dhp = adjust_average(spec_dhp, averages["dhp"]) * 2000
    sr_from_wl = adjust_average(spec_wl, averages["wl"]) * 2000
    sr_from_kda = adjust_average(total_kda, AVERAGE_KDA) * 1000
    sr = round(sr_from_dhp + sr_from_wl + sr_from_kda)
    return sr if sr > 0 else None


def apply_spec_win_penalty(spec_sr: Optional[int], spec_wins: int) -> Optional[int]:
    if spec_sr is None:
        return None
    penalty_fraction = spec_win_penalty_fraction(spec_wins)
    return round(spec_sr * (1 - penalty_fraction))


def spec_win_penalty_fraction(spec_wins: int) -> float:
    if spec_wins >= 250:
        return 0.0
    if spec_wins <= 0:
        return 0.5
    return 0.5 * (1 - (spec_wins / 250.0))


def format_penalty_percent(spec_wins: int) -> Optional[str]:
    penalty_percent = spec_win_penalty_fraction(spec_wins) * 100
    if penalty_percent <= 0:
        return None
    rounded = round(penalty_percent, 1)
    if float(rounded).is_integer():
        return f"{int(rounded)}%"
    return f"{rounded:.1f}%"


def calculate_class_sr(spec_srs: List[Optional[int]]) -> Optional[int]:
    sr = round(sum(null_zero(value) for value in spec_srs) / 3.0)
    return sr if sr > 0 else None


def calculate_overall_sr(class_srs: List[Optional[int]]) -> Optional[int]:
    sr = round(sum(null_zero(value) for value in class_srs) / 4.0)
    return sr if sr > 0 else None


def sr_tone(sr: Optional[int]) -> str:
    if sr is None:
        return "tone-bad"
    if sr >= 4000:
        return "tone-red"
    if sr >= 3000:
        return "tone-orange"
    if sr >= 2000:
        return "tone-blue"
    return "tone-white"


def format_sr_value(sr: Optional[int]) -> str:
    return format_number(sr) if sr is not None else "N/A"


def format_record_sr_html(wins: int, losses: int, plays: int, sr: Optional[int], penalty_labels: Optional[List[str]] = None) -> str:
    record_html = f"<span class='tone-good'>{format_number(wins)}W/{format_number(losses)}L ({format_number(plays)} games)</span>"
    labels = [str(label).strip() for label in (penalty_labels or []) if str(label).strip()]
    penalty_suffix = (
        " <span class='tone-warn'>"
        + " + ".join(f"({escape(label)})" for label in labels)
        + "</span>"
    ) if labels and sr is not None else ""
    sr_html = f"<span class='{sr_tone(sr)}'>SR {escape(format_sr_value(sr))}</span>{penalty_suffix}"
    return f"{record_html} | {sr_html}"


def derived_total_plays(warlords: Dict[str, Any]) -> int:
    return sum(safe_int(warlords.get(f"{class_name}_plays")) for class_name in CLASS_ORDER)


def derived_total_losses(warlords: Dict[str, Any]) -> int:
    return max(0, derived_total_plays(warlords) - safe_int(warlords.get("wins")))


def derived_class_losses(warlords: Dict[str, Any], class_name: str) -> int:
    return max(0, safe_int(warlords.get(f"{class_name}_plays")) - safe_int(warlords.get(f"wins_{class_name}")))


def derived_spec_losses(warlords: Dict[str, Any], spec_name: str) -> int:
    return max(0, safe_int(warlords.get(f"{spec_name}_plays")) - safe_int(warlords.get(f"wins_{spec_name}")))


def record_tone(wins: int, losses: int) -> str:
    if wins > losses:
        return "tone-good"
    if losses > wins:
        return "tone-bad"
    return "tone-cyan"


def build_result(player: Dict[str, Any]) -> Dict[str, Any]:
    warlords = (player.get("stats") or {}).get("Battleground")
    if not warlords:
        raise ValueError("This player has no Warlords stats in Hypixel's Battleground data.")

    wins = safe_int(warlords.get("wins"))
    losses = derived_total_losses(warlords)
    kills = safe_int(warlords.get("kills"))
    deaths = safe_int(warlords.get("deaths"))
    played = derived_total_plays(warlords)
    total_kda = rounded_ratio(kills + safe_int(warlords.get("assists")), deaths if deaths > 0 else 1)
    red_team_wins = safe_int(warlords.get("wins_red"))
    blue_team_wins = safe_int(warlords.get("wins_blu"))
    party_bstd_penalty_active = wins >= 300 and red_team_wins > 0 and blue_team_wins >= red_team_wins * 2

    header = {
        "name": player.get("displayname", "Unknown"),
        "rank": get_rank_label(player),
        "rank_segments": get_rank_segments(player),
        "favorite_class": CLASS_META.get(str(warlords.get("chosen_class") or "").lower(), {}).get("label", "Unknown"),
        "coins": format_number(warlords.get("coins")),
        "magic_dust": format_number(warlords.get("magic_dust")),
        "void_shards": format_number(warlords.get("void_shards")),
    }

    left_stats = [
        row("Wins", format_number(wins), "tone-good"),
        row("Losses", format_number(losses), "tone-bad"),
        row("Games Played", format_number(played)),
        row("Kills", format_number(kills), "tone-warn"),
        row("K/D Ratio", ratio(kills, deaths), "tone-warn" if kills >= deaths else "tone-bad"),
        row("W/L Ratio", ratio(wins, losses), "tone-good" if wins >= losses else "tone-bad"),
        row("Win Rate", percent(wins, played), "tone-cyan"),
        row("Win Streak", format_number(warlords.get("win_streak"))),
        row("Dom. Score", format_number(warlords.get("total_domination_score")), "tone-cyan"),
    ]
    right_stats = [
        row("Deaths", format_number(deaths), "tone-bad"),
        row("Assists", format_number(warlords.get("assists")), "tone-cyan"),
        row("MVP Count", format_number(warlords.get("mvp_count")), "tone-warn"),
        row("Damage Dealt", format_number(warlords.get("damage")), "tone-bad"),
        row("Healing Done", format_number(warlords.get("heal")), "tone-good"),
        row("Damage Prevented", format_number(warlords.get("damage_prevented")), "tone-cyan"),
        row("Life Leeched", format_number(warlords.get("life_leeched")), "tone-bad"),
        row("Flag Captured", format_number(warlords.get("flag_conquer_self")), "tone-cyan"),
        row("Flag Returns", format_number(warlords.get("flag_returns")), "tone-cyan"),
    ]
    overall_rows = [{"left": left, "right": right} for left, right in zip(left_stats, right_stats)]

    class_cards: List[Dict[str, Any]] = []
    class_sr_map: Dict[str, Optional[int]] = {}
    class_sr_values: List[Optional[int]] = []
    for class_name in CLASS_ORDER:
        meta = CLASS_META[class_name]
        class_wins = safe_int(warlords.get(f"wins_{class_name}"))
        class_losses = derived_class_losses(warlords, class_name)
        class_plays = safe_int(warlords.get(f"{class_name}_plays"))
        class_dhp_average = calculate_dhp(warlords, class_name, class_plays)
        active_spec = str(warlords.get(f"{class_name}_spec") or meta["specs"][0])
        spec_rows = []
        active_record = "<span class='tone-good'>0W/0L (0 games)</span> | <span class='tone-bad'>SR N/A</span>"
        spec_sr_values: List[Optional[int]] = []
        for spec_name in meta["specs"]:
            spec_wins = safe_int(warlords.get(f"wins_{spec_name}"))
            spec_losses = derived_spec_losses(warlords, spec_name)
            spec_plays = safe_int(warlords.get(f"{spec_name}_plays"))
            base_spec_sr = calculate_spec_sr(warlords, spec_name, total_kda, played)
            spec_sr = apply_spec_win_penalty(base_spec_sr, spec_wins)
            penalty_labels: List[str] = []
            win_penalty_percent = format_penalty_percent(spec_wins) if base_spec_sr is not None else None
            if win_penalty_percent:
                penalty_labels.append(f"{win_penalty_percent} SR Penalty")
            if party_bstd_penalty_active and spec_sr is not None:
                spec_sr = round(spec_sr * 0.5)
                penalty_labels.append("P. BSTD 50% SR Penalty")
            spec_sr_values.append(spec_sr)
            spec_value = format_record_sr_html(spec_wins, spec_losses, spec_plays, spec_sr, penalty_labels)
            if spec_name == active_spec:
                active_record = spec_value
            spec_rows.append({
                "label": SPEC_LABELS[spec_name],
                "value": spec_value,
                "tone": "tone-white",
                "active": spec_name == active_spec,
                "penalty_percent": win_penalty_percent,
                "penalty_text": " + ".join(f"({label})" for label in penalty_labels),
            })

        class_sr = calculate_class_sr(spec_sr_values)
        class_sr_map[class_name] = class_sr
        class_sr_values.append(class_sr)

        class_cards.append({
            "label": meta["label"],
            "theme": meta["theme"],
            "top_rows": [
                row("Level", f"{class_level(warlords, class_name)}/90", level_tone(class_level(warlords, class_name), 90)),
                row("SR", format_number(class_sr) if class_sr is not None else "N/A", sr_tone(class_sr)),
                row("Wins", format_number(class_wins), "tone-good"),
                row("Losses", format_number(class_losses), "tone-bad"),
                row("Played", format_number(class_plays)),
                row("W/L", ratio(class_wins, class_losses), "tone-good" if class_wins >= class_losses else "tone-bad"),
                row("Win %", percent(class_wins, class_plays), "tone-cyan"),
                row("DHP Avg", format_number(class_dhp_average), "tone-cyan"),
            ],
            "dhp_rows": [
                row("Damage", format_number(warlords.get(f"damage_{class_name}")), "tone-bad"),
                row("Healing", format_number(warlords.get(f"heal_{class_name}")), "tone-good"),
                row("Prevented", format_number(warlords.get(f"damage_prevented_{class_name}")), "tone-cyan"),
            ] + ([row("Life Leech", format_number(warlords.get(f"life_leeched_{class_name}")), "tone-bad")] if safe_int(warlords.get(f"life_leeched_{class_name}")) else []),
            "skill_rows": [
                row("First Skill Upgrade", f"{safe_int(warlords.get(f'{class_name}_skill1'))}/9", level_tone(safe_int(warlords.get(f"{class_name}_skill1")), 9)),
                row("Second Skill Upgrade", f"{safe_int(warlords.get(f'{class_name}_skill2'))}/9", level_tone(safe_int(warlords.get(f"{class_name}_skill2")), 9)),
                row("Third Skill Upgrade", f"{safe_int(warlords.get(f'{class_name}_skill3'))}/9", level_tone(safe_int(warlords.get(f"{class_name}_skill3")), 9)),
                row("Fourth Skill Upgrade", f"{safe_int(warlords.get(f'{class_name}_skill4'))}/9", level_tone(safe_int(warlords.get(f"{class_name}_skill4")), 9)),
                row("Ultimate Skill Upgrade", f"{safe_int(warlords.get(f'{class_name}_skill5'))}/9", level_tone(safe_int(warlords.get(f"{class_name}_skill5")), 9)),
            ],
            "passive_rows": [
                row("Health", f"{safe_int(warlords.get(f'{class_name}_health'))}/9", level_tone(safe_int(warlords.get(f"{class_name}_health")), 9)),
                row("Energy", f"{safe_int(warlords.get(f'{class_name}_energy'))}/9", level_tone(safe_int(warlords.get(f"{class_name}_energy")), 9)),
                row("Cooldown", f"{safe_int(warlords.get(f'{class_name}_cooldown'))}/9", level_tone(safe_int(warlords.get(f"{class_name}_cooldown")), 9)),
                row("Crit Chance", f"{safe_int(warlords.get(f'{class_name}_critchance'))}/9", level_tone(safe_int(warlords.get(f"{class_name}_critchance")), 9)),
                row("Crit Mult.", f"{safe_int(warlords.get(f'{class_name}_critmultiplier'))}/9", level_tone(safe_int(warlords.get(f"{class_name}_critmultiplier")), 9)),
            ],
            "active_spec_label": SPEC_LABELS.get(active_spec, active_spec.title()),
            "active_spec_record": active_record,
            "spec_rows": spec_rows,
        })

    overall_sr = calculate_overall_sr(class_sr_values)

    spec_boost_cards = []
    active_boosts = warlords.get("active_boost") if isinstance(warlords.get("active_boost"), dict) else {}
    for class_name in CLASS_ORDER:
        spec_boost_cards.append({
            "label": CLASS_META[class_name]["label"],
            "theme": CLASS_META[class_name]["theme"],
            "specs": [{
                "name": SPEC_LABELS[spec_name],
                "rows": [
                    {
                        "label": f"{label} *" if active_boosts.get(spec_name) == key else label,
                        "value": f"{safe_int(warlords.get(key))}/4",
                        "tone": "tone-pink" if active_boosts.get(spec_name) == key else ("tone-good" if safe_int(warlords.get(key)) >= 4 else "tone-bad"),
                    }
                    for label, key in SPEC_BOOSTS[class_name][spec_name]
                ],
            } for spec_name in CLASS_META[class_name]["specs"]],
        })

    mode_rows = [{"label": label, "wins": format_number(warlords.get(f"wins_{key}")), "kills": format_number(warlords.get(f"kills_{key}")), "blue": format_number(warlords.get(f"wins_{key}_blu")), "red": format_number(warlords.get(f"wins_{key}_red")), "a": format_number(warlords.get(f"wins_{key}_a")), "b": format_number(warlords.get(f"wins_{key}_b"))} for label, key in MODE_META]
    inventory = weapon_lookup_from_warlords(warlords)
    bound_weapon_rows = build_bound_weapon_rows(warlords, inventory)
    current_weapon_id = warlords.get("current_weapon")
    current_weapon_name = resolve_weapon_title_by_id(current_weapon_id, inventory) if inventory else format_number(current_weapon_id)
    current_weapon_tone = resolve_weapon_tone_by_id(current_weapon_id, inventory) if inventory else "tone-white"
    weapon_inventory_groups = group_weapon_cards(build_resolved_weapon_cards(warlords))
    crafting_blocks = [
        {"label": "Crafting", "theme": "mage", "rows": [row("Crafted (Total)", format_number(warlords.get("crafted")), "tone-cyan"), row("Rare", format_number(warlords.get("crafted_rare"))), row("Epic", format_number(warlords.get("crafted_epic")), "tone-pink"), row("Legendary", format_number(warlords.get("crafted_legendary")), "tone-warn"), row("Upgraded", format_number(warlords.get("upgrade_crafted")), "tone-cyan"), row("Legendary Upgraded", format_number(warlords.get("upgrade_crafted_legendary")), "tone-warn"), row("Rerolled", format_number(warlords.get("reroll")), "tone-cyan"), row("Legendary Rerolled", format_number(warlords.get("reroll_legendary")), "tone-good")]},
        {"label": "Salvaging", "theme": None, "rows": [row("Salvaged (Total)", format_number(warlords.get("salvaged_weapons")), "tone-cyan"), row("Common", format_number(warlords.get("salvaged_weapons_common"))), row("Rare", format_number(warlords.get("salvaged_weapons_rare"))), row("Epic", format_number(warlords.get("salvaged_weapons_epic")), "tone-pink"), row("Legendary", format_number(warlords.get("salvaged_weapons_legendary")), "tone-warn"), row("Dust Earned", format_number(warlords.get("salvaged_dust_reward")), "tone-cyan"), row("Shards Earned", format_number(warlords.get("salvaged_shards_reward")), "tone-pink"), row("Repaired (Total)", format_number(warlords.get("repaired")), "tone-cyan"), row("Common Repaired", format_number(warlords.get("repaired_common"))), row("Rare Repaired", format_number(warlords.get("repaired_rare")), "tone-cyan"), row("Epic Repaired", format_number(warlords.get("repaired_epic")), "tone-pink"), row("Legendary Repaired", format_number(warlords.get("repaired_legendary")), "tone-warn")]},
        {"label": "Equipped", "theme": "paladin", "rows": [row("Current Weapon", current_weapon_name, current_weapon_tone), row("Selected Mount", prettify_identifier(warlords.get("selected_mount")))], "bound_rows": bound_weapon_rows},
    ]

    used = set(SKIP_EXACT)
    for class_name in CLASS_ORDER:
        used.update({f"wins_{class_name}", f"losses_{class_name}", f"{class_name}_plays", f"damage_{class_name}", f"heal_{class_name}", f"damage_prevented_{class_name}", f"life_leeched_{class_name}", f"{class_name}_spec"})
        used.update({f"{class_name}_skill{i}" for i in range(1, 6)})
        used.update({f"{class_name}_{suffix}" for suffix in ("health", "energy", "cooldown", "critchance", "critmultiplier")})
        for spec_name in CLASS_META[class_name]["specs"]:
            used.update({f"wins_{spec_name}", f"losses_{spec_name}", f"{spec_name}_plays", f"damage_{spec_name}", f"heal_{spec_name}", f"damage_prevented_{spec_name}", f"life_leeched_{spec_name}"})
            used.update(key for _, key in SPEC_BOOSTS[class_name][spec_name])
    for _, key in MODE_META:
        used.update({f"wins_{key}", f"kills_{key}", f"wins_{key}_blu", f"wins_{key}_red", f"wins_{key}_a", f"wins_{key}_b"})
    used.update({"crafted", "crafted_rare", "crafted_epic", "crafted_legendary", "upgrade_crafted", "upgrade_crafted_legendary", "reroll", "reroll_legendary", "salvaged_weapons", "salvaged_weapons_common", "salvaged_weapons_rare", "salvaged_weapons_epic", "salvaged_weapons_legendary", "salvaged_dust_reward", "salvaged_shards_reward", "repaired", "repaired_common", "repaired_rare", "repaired_epic", "repaired_legendary"})
    advanced_rows = []
    seen_other_field_keys = set()
    for key in sorted(warlords):
        value = warlords[key]
        normalized_key = str(key or "").strip().lower()
        canonical_key = OTHER_FIELD_CANONICAL_KEYS.get(normalized_key, normalized_key)
        if key in used or isinstance(value, (dict, list)):
            continue
        if canonical_key in OTHER_FIELD_SKIP_EXACT or canonical_key in seen_other_field_keys:
            continue
        if any(fragment in key.lower() for fragment in SKIP_SUBSTRINGS):
            continue
        if not value and value not in (False, 0):
            continue
        tone = "tone-bad" if any(word in canonical_key for word in ("loss", "death", "penalty")) else "tone-cyan" if any(word in canonical_key for word in ("damage", "shard", "returns", "conquer", "dom", "powerup")) else "tone-white"
        advanced_rows.append(row(labelize(canonical_key), format_number(value), tone))
        seen_other_field_keys.add(canonical_key)
    advanced_rows.sort(key=lambda entry: str(entry.get("label") or ""))

    metadata = []
    for key, label in (("active_boost", "Active Boost Loadout"), ("leaderboardSettings", "Leaderboard Settings")):
        value = warlords.get(key)
        if isinstance(value, dict):
            metadata.append({"label": label, "rows": flatten_metadata(value)})

    return {
        "header": header,
        "overall_sr": format_number(overall_sr) if overall_sr is not None else "N/A",
        "overall_sr_tone": sr_tone(overall_sr),
        "leaderboard_scores": {
            "overall": overall_sr,
            **class_sr_map,
        },
        "overall_rows": overall_rows,
        "class_cards": class_cards,
        "spec_boost_cards": spec_boost_cards,
        "mode_rows": mode_rows,
        "crafting_blocks": crafting_blocks,
        "advanced_rows": advanced_rows,
        "metadata": metadata,
        "weapon_inventory_groups": weapon_inventory_groups,
        "extra_stats": {
            "flag_captured": format_number(warlords.get("flag_conquer_self")),
            "flag_returns": format_number(warlords.get("flag_returns")),
            "dom_point_captures": format_number(warlords.get("dom_point_captures")),
            "dom_point_defends": format_number(warlords.get("dom_point_defends")),
        },
    }


def flatten_metadata(value: Any, prefix: str = "") -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            next_prefix = f"{prefix} / {labelize(str(key))}" if prefix else labelize(str(key))
            rows.extend(flatten_metadata(child, next_prefix))
        return rows
    if isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(flatten_metadata(child, f"{prefix} / {index}"))
        return rows
    rows.append(row(prefix, format_number(value), "tone-cyan"))
    return rows


def lookup_player_result(username: str) -> Dict[str, Any]:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ValueError("Please provide a Minecraft username.")
    return build_result(fetch_hypixel_player(fetch_uuid_for_username(normalized_username)))


def lookup_player_result_by_uuid(player_uuid: str) -> Dict[str, Any]:
    normalized_uuid = normalize_player_uuid(player_uuid)
    return build_result(fetch_hypixel_player(normalized_uuid))


def lookup_player_result_by_identifier(player_identifier: str) -> Dict[str, Any]:
    normalized_identifier = str(player_identifier or "").strip()
    if not normalized_identifier:
        raise ValueError("Please provide a Minecraft username or UUID.")
    if UUID_PATTERN.fullmatch(normalized_identifier):
        return lookup_player_result_by_uuid(normalized_identifier)
    return lookup_player_result(normalized_identifier)


def render_result_page(
    query: str = "",
    error: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
    snapshot_mode: bool = False,
) -> str:
    with app.app_context():
        return render_template(
            "index.html",
            title=APP_TITLE,
            query=query,
            error=error,
            result=result,
            snapshot_mode=snapshot_mode,
        )


def render_custom_template(template_name: str, **context: Any) -> str:
    with app.app_context():
        return render_template(template_name, **context)


@app.route("/", methods=["GET"])
def index():
    query = (request.args.get("player") or "").strip()
    error = None
    result = None
    if query:
        try:
            result = lookup_player_result(query)
        except ValueError as exc:
            error = str(exc)
    return render_result_page(query=query, error=error, result=result)


def run_web_app(host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
    app.run(debug=debug, host=host, port=port, use_reloader=False)


if __name__ == "__main__":
    run_web_app(debug=True)
