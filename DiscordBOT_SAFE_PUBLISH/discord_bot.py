import asyncio
import contextlib
import io
import json
import logging
import math
import os
import re
import threading
import time
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from app import (
    fetch_uuid_for_username,
    load_env_file,
    lookup_player_result,
    lookup_player_result_by_uuid,
    render_custom_template,
)

try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright
except ImportError:
    PlaywrightError = RuntimeError
    async_playwright = None


APP_NAME = "Warlords Lookup Bot"
CARD_SELECTOR = "#discord-card"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,16}$")
UUID_PATTERN = re.compile(
    r"^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)
LOOKUP_CACHE_TTL_SECONDS = 60.0
SECTION_CACHE_TTL_SECONDS = 60.0
MAX_DISCORD_ATTACHMENT_BYTES = 8_000_000
PLAYER_DESCRIPTIONS_FILE = Path(__file__).with_name("player_descriptions.json")
LEADERBOARD_CACHE_FILE = Path(__file__).with_name("leaderboard_cache.json")
LEADERBOARD_BANNED_FILE = Path(__file__).with_name("leaderboard_banned_players.json")
SEASON_TRACKING_FILE = Path(__file__).with_name("season_tracking_players.txt")
SEASON_STATE_FILE = Path(__file__).with_name("seasonlb_state.json")
OLD_SEASONS_DIR = Path(__file__).with_name("OldSeasons")
DEFAULT_PLAYER_DESCRIPTION = "Teishoko hasnt given an opinion on this LARP yet, be better bro."
LEADERBOARD_REFRESH_SECONDS = 86400.0
LEADERBOARD_MAX_PLAYERS = 25
SEASON_REFRESH_SECONDS = 86400.0
SEASON_MIN_GAMES_VISIBLE = 10
SEASON_MAX_TRACKED_GAMES = 1000
SEASON_WSR_CAP = 5000
SEASON_WSR_MAX_WLR = 3.0
RESULT_CACHE_SCHEMA_VERSION = 2
LOOKUP_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
SECTION_IMAGE_CACHE: Dict[str, Tuple[float, bytes, str]] = {}
LOOKUP_CACHE_LOCK = threading.Lock()
SECTION_IMAGE_CACHE_LOCK = threading.Lock()
LEADERBOARD_CACHE_LOCK = threading.Lock()
SEASON_STATE_LOCK = threading.Lock()
LOOKUP_SEMAPHORE = asyncio.Semaphore(3)
THEME_COLORS = {
    "warrior": discord.Color.from_rgb(255, 95, 118),
    "paladin": discord.Color.from_rgb(255, 212, 82),
    "mage": discord.Color.from_rgb(103, 232, 255),
    "shaman": discord.Color.from_rgb(98, 255, 141),
}
THEME_STYLE = {
    "warrior": {"color": "#ff5f76", "soft": "rgba(255,95,118,.18)"},
    "paladin": {"color": "#ffd452", "soft": "rgba(255,212,82,.18)"},
    "mage": {"color": "#67e8ff", "soft": "rgba(103,232,255,.18)"},
    "shaman": {"color": "#62ff8d", "soft": "rgba(98,255,141,.18)"},
}
FAVORITE_CLASS_TO_THEME = {
    "Warrior": "warrior",
    "Paladin": "paladin",
    "Mage": "mage",
    "Shaman": "shaman",
}
LEADERBOARD_SCOPE_META = {
    "overall": {"label": "Overall SR", "theme": "mage"},
    "mage": {"label": "Mage Overall SR", "theme": "mage"},
    "warrior": {"label": "Warrior Overall SR", "theme": "warrior"},
    "paladin": {"label": "Paladin Overall SR", "theme": "paladin"},
    "shaman": {"label": "Shaman Overall SR", "theme": "shaman"},
}
LEADERBOARD_SCOPE_SPECS = {
    "mage": ["Pyromancer", "Cryomancer", "Aquamancer"],
    "warrior": ["Berserker", "Defender", "Revenant"],
    "paladin": ["Avenger", "Crusader", "Protector"],
    "shaman": ["Thunderlord", "Spiritguard", "Earthwarden"],
}
LEADERBOARD_SECTIONS = [
    {"key": "overall", "label": "Overall SR", "short": "Overall"},
    {"key": "mage", "label": "Mage SR", "short": "Mage"},
    {"key": "warrior", "label": "Warrior SR", "short": "Warrior"},
    {"key": "paladin", "label": "Paladin SR", "short": "Paladin"},
    {"key": "shaman", "label": "Shaman SR", "short": "Shaman"},
]
LEADERBOARD_OVERALL_DESCRIPTION = "The way the Overall SR leaderboard work is that it takes ALL classes SR (Mage, Warrior, Paladin and Shaman) and combining them makes an average number giving max stats of: 2000 DHP, 2000 WLR And 1000 KDR, having a maximum of 5000 SR, and if you think your Overall SR is low its because you might not play some other specializations and it gives you penalty (check /sr <playername>)"
LEADERBOARD_CLASS_DESCRIPTION = "The Classes SR Score is calculated by uniting all the three specializations into a single SR, Following this math: 2000 DHP 2000 WLR 1000 KDR, where you can have a maximum of 5000 SR, if you think you SR Is low it might be because you only play one specialization or two and you have a penalty in another, because the SR conts all 3 specializations. To check for penalties do /sr <playername>"
LEADERBOARD_SPEC_DESCRIPTION = "Each Specialization has their own SR, This SR counts DHP For a Maximum of 2000, WLR 2000, and KDR 1000, for a maximum total count of 5000 sr. This LB Calculates only the current specialization."
SEASON_RULES_DESCRIPTION = (
    "Each actual season tracks up to 1000 games per player. WSR is based only on seasonal Win/Loss ratio. "
    f"Players unlock leaderboard eligibility after {SEASON_MIN_GAMES_VISIBLE} tracked games."
)
SEASON_NAME_LABELS = {
    "winter": "Winter",
    "spring": "Spring",
    "summer": "Summer",
    "autumn": "Autumn",
}
SECTION_DEFINITIONS = [
    {"key": "overall_statistics", "label": "Overall Statistics", "short": "Overall", "kicker": "Performance Core", "description": "The fast read. Record, efficiency, volume, and first-impression numbers.", "note": ""},
    {"key": "class_and_sr_breakdown", "label": "Class And SR Breakdown", "short": "Class & SR", "kicker": "Ratings And Classes", "description": "Class level, SR, DHP, and specialization SR in one clear page.", "note": ""},
    {"key": "game_mode_breakdown", "label": "Game Modes Breakdown", "short": "Modes", "kicker": "Mode Performance", "description": "Capture the Flag, Domination, and Team Deathmatch with mode-specific fields.", "note": ""},
    {"key": "crafting_equipment", "label": "Crafting & Equipment", "short": "Crafting", "kicker": "Progression And Inventory", "description": "Current gear, mounts, bound weapons, salvaging, crafting, and rerolls together.", "note": ""},
    {"key": "weapon_inv_war_pal", "label": "Weapon INV War/Pal", "short": "War/Pal Weapons", "kicker": "Resolved Weapons", "description": "Warrior and Paladin inventory cards, separated for easier reading.", "note": ""},
    {"key": "weapon_inv_mag_sha", "label": "Weapon INV Mag/Sha", "short": "Mag/Sha Weapons", "kicker": "Resolved Weapons", "description": "Mage and Shaman inventory cards, separated for easier reading.", "note": ""},
    {"key": "spec_boost_war_pal", "label": "Spec Boost War/Pal", "short": "War/Pal Boost", "kicker": "Loadout Details", "description": "Warrior and Paladin specialization boosts, split off so the upgrade paths stay readable.", "note": ""},
    {"key": "spec_boost_mag_sha", "label": "Spec Boost Mag/Sha", "short": "Mag/Sha Boost", "kicker": "Loadout Details", "description": "Mage and Shaman specialization boosts with enough breathing room to actually compare them.", "note": ""},
    {"key": "other_tracked_fields", "label": "Other Tracked Fields", "short": "Other Fields", "kicker": "Extended Stats", "description": "The deep-cut leftovers: extra counters, utility fields, and odd numbers worth keeping.", "note": ""},
]
SECTION_BY_KEY = {section["key"]: section for section in SECTION_DEFINITIONS}
SECTION_INDEX = {section["key"]: index for index, section in enumerate(SECTION_DEFINITIONS)}
OVERALL_STAT_PAIRS = [
    (
        {"source": "Wins", "label": "Wins", "tone": "tone-good"},
        {"source": "Deaths", "label": "Deaths", "tone": "tone-bad"},
    ),
    (
        {"source": "Losses", "label": "Losses", "tone": "tone-bad"},
        {"source": "Assists", "label": "Assists", "tone": "tone-cyan"},
    ),
    (
        {"source": "Games Played", "label": "Games Played", "tone": "tone-white"},
        {"source": "MVP Count", "label": "MVP Count", "tone": "tone-warn"},
    ),
    (
        {"source": "Kills", "label": "Kills", "tone": "tone-warn"},
        {"source": "Damage Dealt", "label": "Damage Dealt", "tone": "tone-bad"},
    ),
    (
        {"source": "K/D Ratio", "label": "K/D Ratio", "tone": "tone-warn"},
        {"source": "Healing Done", "label": "Healing Done", "tone": "tone-good"},
    ),
    (
        {"source": "W/L Ratio", "label": "W/L Ratio", "tone": "tone-good"},
        {"source": "Damage Prevented", "label": "Damage Prevented", "tone": "tone-cyan"},
    ),
    (
        {"source": "Win Rate", "label": "Win Rate", "tone": "tone-cyan"},
        {"source": "Life Leeched", "label": "Life Leeched", "tone": "tone-bad"},
    ),
    (
        {"source": "Win Streak", "label": "Win Streak", "tone": "tone-white"},
        {"source": "Flag Captured", "label": "Flag Captured", "tone": "tone-cyan"},
    ),
    (
        {"source": "Dom. Score", "label": "Dom. Score", "tone": "tone-cyan"},
        {"source": "Flag Returns", "label": "Flag Returns", "tone": "tone-cyan"},
    ),
]
OVERALL_DUPLICATE_LABELS = {
    metric["source"]
    for left_metric, right_metric in OVERALL_STAT_PAIRS
    for metric in (left_metric, right_metric)
}


def validate_username(username: str) -> str:
    normalized = str(username or "").strip()
    if not normalized:
        raise ValueError("Please provide a Minecraft username.")
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("Minecraft usernames must be 1-16 characters and use only letters, numbers, or underscores.")
    return normalized


def sanitize_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return normalized or "warlords-player"


def trim_text(value: str, limit: int = 1024) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}..."


def load_discord_token() -> str:
    return os.environ.get("DISCORD_BOT_TOKEN", "").strip()


def strip_html_tags(value: Any) -> str:
    text = unescape(str(value or ""))
    return re.sub(r"<[^>]+>", "", text).strip()


def load_player_descriptions() -> Dict[str, str]:
    if not PLAYER_DESCRIPTIONS_FILE.exists():
        return {}
    try:
        payload = json.loads(PLAYER_DESCRIPTIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key).strip().lower(): str(value).strip() for key, value in payload.items() if str(key).strip() and str(value).strip()}


def player_description(username: str) -> str:
    descriptions = load_player_descriptions()
    return descriptions.get(username.strip().lower(), DEFAULT_PLAYER_DESCRIPTION)


def load_banned_leaderboard_players() -> set[str]:
    if not LEADERBOARD_BANNED_FILE.exists():
        return set()
    try:
        payload = json.loads(LEADERBOARD_BANNED_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(payload, list):
        return set()
    return {str(item).strip().lower() for item in payload if str(item).strip()}


def load_leaderboard_cache() -> Dict[str, Dict[str, Any]]:
    if not LEADERBOARD_CACHE_FILE.exists():
        return {}
    try:
        payload = json.loads(LEADERBOARD_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        normalized_key = str(key or "").strip().lower()
        if not normalized_key:
            continue
        normalized[normalized_key] = value
    return normalized


def save_leaderboard_cache(entries: Dict[str, Dict[str, Any]]) -> None:
    temp_file = LEADERBOARD_CACHE_FILE.with_suffix(f"{LEADERBOARD_CACHE_FILE.suffix}.tmp")
    temp_file.write_text(json.dumps(entries, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(temp_file, LEADERBOARD_CACHE_FILE)


def leaderboard_entry_key(username: str) -> str:
    return validate_username(username).lower()


def result_updated_at(result: Dict[str, Any]) -> float:
    return float((result.get("_cache") or {}).get("updated_at") or 0.0)


def result_schema_version(result: Dict[str, Any]) -> int:
    return int((result.get("_cache") or {}).get("schema_version") or 0)


def is_result_cache_compatible(result: Dict[str, Any]) -> bool:
    return result_schema_version(result) == RESULT_CACHE_SCHEMA_VERSION


def with_result_timestamp(result: Dict[str, Any], updated_at: float) -> Dict[str, Any]:
    stamped = json.loads(json.dumps(result))
    stamped["_cache"] = {
        "updated_at": float(updated_at),
        "schema_version": RESULT_CACHE_SCHEMA_VERSION,
    }
    return stamped


def save_result_to_leaderboard_cache(result: Dict[str, Any], updated_at: Optional[float] = None) -> Dict[str, Any]:
    header = result.get("header") or {}
    player_name = str(header.get("name") or "").strip()
    if not player_name:
        return result
    timestamp = float(updated_at or time.time())
    stored_result = with_result_timestamp(result, timestamp)
    entry = {
        "username": player_name,
        "updated_at": timestamp,
        "scores": stored_result.get("leaderboard_scores") or {},
        "result": stored_result,
    }
    with LEADERBOARD_CACHE_LOCK:
        entries = load_leaderboard_cache()
        entries[player_name.lower()] = entry
        save_leaderboard_cache(entries)
    return stored_result


def get_saved_result(username: str) -> Optional[Dict[str, Any]]:
    with LEADERBOARD_CACHE_LOCK:
        entry = load_leaderboard_cache().get(leaderboard_entry_key(username))
    if not entry:
        return None
    result = entry.get("result")
    return result if isinstance(result, dict) else None


def leaderboard_score(result: Dict[str, Any], scope_key: str) -> Optional[int]:
    scores = result.get("leaderboard_scores")
    if isinstance(scores, dict):
        value = scores.get(scope_key)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(round(value))
    if scope_key == "overall":
        value = str(result.get("overall_sr") or "").replace(",", "").strip().upper()
        return int(value) if value.isdigit() else None
    for class_card in result.get("class_cards") or []:
        label = str(class_card.get("label") or "").strip().lower()
        if label != scope_key:
            continue
        for row in class_card.get("top_rows") or []:
            if str(row.get("label") or "") != "SR":
                continue
            value = str(row.get("value") or "").replace(",", "").strip().upper()
            return int(value) if value.isdigit() else None
    return None


def cached_lookup(username: str) -> Dict[str, Any]:
    normalized = validate_username(username)
    key = normalized.lower()
    now = time.time()
    with LOOKUP_CACHE_LOCK:
        cached = LOOKUP_CACHE.get(key)
        if cached and now - cached[0] <= LOOKUP_CACHE_TTL_SECONDS:
            return cached[1]

    saved_result = get_saved_result(normalized)
    saved_updated_at = result_updated_at(saved_result) if saved_result else 0.0
    if (
        saved_result
        and is_result_cache_compatible(saved_result)
        and now - saved_updated_at <= LEADERBOARD_REFRESH_SECONDS
    ):
        with LOOKUP_CACHE_LOCK:
            LOOKUP_CACHE[key] = (time.time(), saved_result)
        return saved_result

    try:
        result = lookup_player_result(normalized)
        result = save_result_to_leaderboard_cache(result, updated_at=now)
    except Exception:
        if saved_result is not None:
            logging.warning("Falling back to stale saved result for %s after lookup failure", normalized, exc_info=True)
            with LOOKUP_CACHE_LOCK:
                LOOKUP_CACHE[key] = (time.time(), saved_result)
            return saved_result
        raise

    with LOOKUP_CACHE_LOCK:
        LOOKUP_CACHE[key] = (time.time(), result)
    return result


def flatten_overall_rows(result: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for pair in result.get("overall_rows") or []:
        if isinstance(pair, dict):
            left = pair.get("left")
            right = pair.get("right")
            if isinstance(left, dict):
                rows.append(left)
            if isinstance(right, dict):
                rows.append(right)
    return rows


def find_row(rows: List[Dict[str, str]], label: str) -> Dict[str, str]:
    for row in rows:
        if str(row.get("label")) == label:
            return row
    return {"label": label, "value": "0", "tone": "tone-white"}


def find_row_value(rows: List[Dict[str, str]], label: str, default: str = "0") -> str:
    return str(find_row(rows, label).get("value") or default)


def favorite_theme_key(result: Dict[str, Any]) -> str:
    favorite_class = ((result.get("header") or {}).get("favorite_class") or "").strip()
    return FAVORITE_CLASS_TO_THEME.get(favorite_class, "mage")


def favorite_class_color(result: Dict[str, Any]) -> discord.Color:
    return THEME_COLORS.get(favorite_theme_key(result), discord.Color.blurple())


def rank_tone(rank: str) -> str:
    if rank == "[MVP++]":
        return "tone-warn"
    if rank == "[MVP+]":
        return "tone-cyan"
    if rank == "[MVP]":
        return "tone-blue"
    if rank in {"[VIP+]", "[VIP]"}:
        return "tone-good"
    return "tone-white"


def sr_display_tone(value: str) -> str:
    normalized = str(value or "").replace(",", "").strip().upper()
    if normalized in {"", "N/A"}:
        return "tone-white"
    try:
        numeric = int(float(normalized))
    except ValueError:
        return "tone-white"
    if numeric >= 4000:
        return "tone-red"
    if numeric >= 3000:
        return "tone-orange"
    if numeric >= 2000:
        return "tone-blue"
    return "tone-white"


def normalize_uuid(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "")
    if not re.fullmatch(r"[0-9a-f]{32}", normalized):
        raise ValueError("Invalid UUID.")
    return normalized


def parse_numeric_int(value: Any, default: int = 0) -> int:
    digits = re.sub(r"[^0-9-]", "", str(value or "").strip())
    if not digits or digits in {"-", "--"}:
        return default
    try:
        return int(digits)
    except ValueError:
        return default


def format_ordinal(value: int) -> str:
    number = int(value)
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def season_descriptor(now: Optional[datetime] = None) -> Dict[str, Any]:
    current = (now or datetime.now().astimezone()).astimezone()
    month = current.month
    year = current.year
    tz = current.tzinfo
    if month in (12, 1, 2):
        family = "winter"
        start_year = year if month == 12 else year - 1
        start = datetime(start_year, 12, 1, tzinfo=tz)
        end = datetime(start_year + 1, 3, 1, tzinfo=tz)
    elif month in (3, 4, 5):
        family = "spring"
        start = datetime(year, 3, 1, tzinfo=tz)
        end = datetime(year, 6, 1, tzinfo=tz)
    elif month in (6, 7, 8):
        family = "summer"
        start = datetime(year, 6, 1, tzinfo=tz)
        end = datetime(year, 9, 1, tzinfo=tz)
    else:
        family = "autumn"
        start = datetime(year, 9, 1, tzinfo=tz)
        end = datetime(year, 12, 1, tzinfo=tz)
    return {
        "family": family,
        "label": SEASON_NAME_LABELS[family],
        "start": start,
        "end": end,
        "start_unix": start.timestamp(),
        "end_unix": end.timestamp(),
        "start_key": start.strftime("%Y-%m-%d"),
    }


def default_season_state() -> Dict[str, Any]:
    return {
        "active_season_key": "",
        "season_editions": {},
        "seasons": {},
    }


def load_season_state() -> Dict[str, Any]:
    if not SEASON_STATE_FILE.exists():
        return default_season_state()
    try:
        payload = json.loads(SEASON_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_season_state()
    if not isinstance(payload, dict):
        return default_season_state()
    state = default_season_state()
    state["active_season_key"] = str(payload.get("active_season_key") or "")
    editions = payload.get("season_editions")
    state["season_editions"] = editions if isinstance(editions, dict) else {}
    seasons = payload.get("seasons")
    state["seasons"] = seasons if isinstance(seasons, dict) else {}
    return state


def save_season_state(state: Dict[str, Any]) -> None:
    temp = SEASON_STATE_FILE.with_suffix(f"{SEASON_STATE_FILE.suffix}.tmp")
    temp.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(temp, SEASON_STATE_FILE)


def ensure_active_season(state: Dict[str, Any], now: Optional[datetime] = None) -> Tuple[Dict[str, Any], Optional[str]]:
    descriptor = season_descriptor(now)
    seasons = state.setdefault("seasons", {})
    editions = state.setdefault("season_editions", {})
    active_key = str(state.get("active_season_key") or "")
    archived_key: Optional[str] = None

    active_record = seasons.get(active_key) if active_key else None
    active_matches = (
        isinstance(active_record, dict)
        and str(active_record.get("family") or "") == descriptor["family"]
        and str(active_record.get("start_key") or "") == descriptor["start_key"]
    )
    if active_matches:
        return active_record, None

    existing_match: Optional[Dict[str, Any]] = None
    for record in seasons.values():
        if not isinstance(record, dict):
            continue
        if str(record.get("family") or "") != descriptor["family"]:
            continue
        if str(record.get("start_key") or "") != descriptor["start_key"]:
            continue
        existing_match = record
        break
    if existing_match is not None:
        state["active_season_key"] = str(existing_match.get("season_key") or "")
        return existing_match, None

    now_unix = datetime.now().astimezone().timestamp()
    if isinstance(active_record, dict):
        active_record["ended_unix"] = now_unix
        if str(active_record.get("archive_status") or "") not in {"done"}:
            active_record["archive_status"] = "pending"
            safe_title = sanitize_filename(str(active_record.get("title") or active_key)).lower()
            active_record["archive_filename"] = active_record.get("archive_filename") or f"{safe_title}.png"
            archived_key = active_key

    edition = int(editions.get(descriptor["family"]) or 0) + 1
    editions[descriptor["family"]] = edition
    season_key = f"{descriptor['family']}-{descriptor['start'].strftime('%Y')}-e{edition}"
    season_record = {
        "season_key": season_key,
        "family": descriptor["family"],
        "label": descriptor["label"],
        "edition": edition,
        "title": f"{descriptor['label']} Season {format_ordinal(edition)} Edition",
        "start_key": descriptor["start_key"],
        "start_unix": descriptor["start_unix"],
        "end_unix": descriptor["end_unix"],
        "next_refresh_unix": descriptor["start_unix"] + SEASON_REFRESH_SECONDS,
        "last_refresh_unix": 0.0,
        "created_unix": now_unix,
        "archive_status": "",
        "archive_filename": "",
        "tracked_uuids": [],
        "players": {},
        "last_refresh_summary": {},
    }
    seasons[season_key] = season_record
    state["active_season_key"] = season_key
    return season_record, archived_key


def parse_tracking_file_entries() -> List[str]:
    if not SEASON_TRACKING_FILE.exists():
        return []
    entries: List[str] = []
    for raw_line in SEASON_TRACKING_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return entries


def resolve_tracking_entry_to_uuid(entry: str) -> str:
    candidate = str(entry or "").strip()
    if UUID_PATTERN.fullmatch(candidate):
        return normalize_uuid(candidate)
    username = validate_username(candidate)
    return normalize_uuid(fetch_uuid_for_username(username))


def resolve_tracking_uuids() -> Tuple[List[str], List[str]]:
    ordered: List[str] = []
    seen: set[str] = set()
    errors: List[str] = []
    for raw_entry in parse_tracking_file_entries():
        try:
            normalized_uuid = resolve_tracking_entry_to_uuid(raw_entry)
        except Exception as exc:
            errors.append(f"{raw_entry}: {exc}")
            continue
        if normalized_uuid in seen:
            continue
        seen.add(normalized_uuid)
        ordered.append(normalized_uuid)
    return ordered, errors


def season_player_wlr(tracked_wins: int, tracked_losses: int) -> float:
    if tracked_losses <= 0:
        return float("inf") if tracked_wins > 0 else 0.0
    return tracked_wins / tracked_losses


def season_wsr_from_wlr(wlr: float) -> int:
    if math.isinf(wlr):
        return SEASON_WSR_CAP
    if wlr <= 0:
        return 0
    return min(SEASON_WSR_CAP, int(round((wlr / SEASON_WSR_MAX_WLR) * SEASON_WSR_CAP)))


def season_wlr_text(wlr: float) -> str:
    if math.isinf(wlr):
        return "INF"
    return f"{wlr:.2f}"


def season_refresh_due(season: Dict[str, Any], now_unix: float, force: bool) -> bool:
    if force:
        return True
    next_refresh = float(season.get("next_refresh_unix") or 0.0)
    last_refresh = float(season.get("last_refresh_unix") or 0.0)
    if last_refresh <= 0:
        return True
    return now_unix >= next_refresh


def apply_season_refresh(season: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    now_unix = datetime.now().astimezone().timestamp()
    if not season_refresh_due(season, now_unix, force):
        return {
            "performed": False,
            "reason": "not_due",
            "tracked_count": len(season.get("tracked_uuids") or []),
            "eligible_count": len([player for player in (season.get("players") or {}).values() if int(player.get("tracked_games") or 0) >= SEASON_MIN_GAMES_VISIBLE]),
        }

    tracked_uuids, tracking_errors = resolve_tracking_uuids()
    season["tracked_uuids"] = tracked_uuids
    players = season.setdefault("players", {})

    refreshed = 0
    errors = list(tracking_errors)
    changed = 0
    frozen_count = 0
    for index, player_uuid in enumerate(tracked_uuids):
        entry = players.get(player_uuid)
        if not isinstance(entry, dict):
            entry = {
                "uuid": player_uuid,
                "order_index": index,
                "display_name": player_uuid[:12],
                "tracked_wins": 0,
                "tracked_losses": 0,
                "tracked_games": 0,
                "frozen": False,
                "baseline": None,
                "latest": None,
                "last_update_unix": 0.0,
                "last_error": "",
            }
            players[player_uuid] = entry
        entry["order_index"] = index
        if bool(entry.get("frozen")) or int(entry.get("tracked_games") or 0) >= SEASON_MAX_TRACKED_GAMES:
            entry["frozen"] = True
            frozen_count += 1
            continue
        try:
            result = lookup_player_result_by_uuid(player_uuid)
        except Exception as exc:
            entry["last_error"] = str(exc)
            errors.append(f"{player_uuid}: {exc}")
            continue

        refreshed += 1
        entry["last_error"] = ""
        display_name = str(((result.get("header") or {}).get("name") or player_uuid)).strip() or player_uuid
        wins = parse_numeric_int(find_row_value(summary_rows(result), "Wins", "0"))
        losses = parse_numeric_int(find_row_value(summary_rows(result), "Losses", "0"))
        total_games = max(0, wins + losses)
        current_snapshot = {
            "wins": wins,
            "losses": losses,
            "total_games": total_games,
            "timestamp": now_unix,
        }
        entry["display_name"] = display_name
        entry["last_update_unix"] = now_unix

        latest = entry.get("latest")
        if not isinstance(latest, dict):
            entry["baseline"] = current_snapshot
            entry["latest"] = current_snapshot
            continue

        prev_wins = int(latest.get("wins") or 0)
        prev_losses = int(latest.get("losses") or 0)
        delta_wins = max(0, wins - prev_wins)
        delta_losses = max(0, losses - prev_losses)
        delta_games = delta_wins + delta_losses
        entry["latest"] = current_snapshot
        if delta_games <= 0:
            continue

        tracked_games = int(entry.get("tracked_games") or 0)
        remaining = max(0, SEASON_MAX_TRACKED_GAMES - tracked_games)
        if remaining <= 0:
            entry["frozen"] = True
            frozen_count += 1
            continue

        applied_games = min(delta_games, remaining)
        if applied_games == delta_games:
            applied_wins = delta_wins
            applied_losses = delta_losses
        else:
            applied_wins = int(round((delta_wins / delta_games) * applied_games))
            applied_wins = max(0, min(applied_wins, applied_games))
            applied_losses = applied_games - applied_wins

        if applied_games > 0:
            entry["tracked_wins"] = int(entry.get("tracked_wins") or 0) + applied_wins
            entry["tracked_losses"] = int(entry.get("tracked_losses") or 0) + applied_losses
            entry["tracked_games"] = int(entry.get("tracked_games") or 0) + applied_games
            changed += applied_games

        if int(entry.get("tracked_games") or 0) >= SEASON_MAX_TRACKED_GAMES:
            entry["tracked_games"] = SEASON_MAX_TRACKED_GAMES
            entry["frozen"] = True
            frozen_count += 1

    next_refresh = float(season.get("next_refresh_unix") or (float(season.get("start_unix") or now_unix) + SEASON_REFRESH_SECONDS))
    while next_refresh <= now_unix:
        next_refresh += SEASON_REFRESH_SECONDS
    season["next_refresh_unix"] = next_refresh
    season["last_refresh_unix"] = now_unix

    eligible_count = 0
    for uuid in season.get("tracked_uuids") or []:
        player_entry = players.get(uuid)
        if not isinstance(player_entry, dict):
            continue
        if int(player_entry.get("tracked_games") or 0) >= SEASON_MIN_GAMES_VISIBLE:
            eligible_count += 1

    summary = {
        "performed": True,
        "tracked_count": len(tracked_uuids),
        "refreshed_count": refreshed,
        "eligible_count": eligible_count,
        "changed_games": changed,
        "frozen_count": frozen_count,
        "error_count": len(errors),
        "errors": errors,
        "refreshed_at_unix": now_unix,
    }
    season["last_refresh_summary"] = summary
    return summary


def season_refresh_snapshot(season: Dict[str, Any], reason: str = "not_requested") -> Dict[str, Any]:
    players = season.get("players") or {}
    eligible_count = 0
    if isinstance(players, dict):
        for player in players.values():
            if not isinstance(player, dict):
                continue
            if int(player.get("tracked_games") or 0) >= SEASON_MIN_GAMES_VISIBLE:
                eligible_count += 1
    return {
        "performed": False,
        "reason": reason,
        "tracked_count": len(season.get("tracked_uuids") or []),
        "eligible_count": eligible_count,
    }


def update_season_state(force_refresh: bool = False, refresh_stats: bool = True) -> Dict[str, Any]:
    with SEASON_STATE_LOCK:
        state = load_season_state()
        active_season, archived_key = ensure_active_season(state)
        if refresh_stats:
            refresh_summary = apply_season_refresh(active_season, force=force_refresh)
        else:
            refresh_summary = season_refresh_snapshot(active_season, reason="refresh_disabled")
        save_season_state(state)
        return {
            "active_season_key": str(state.get("active_season_key") or ""),
            "active_season_title": str(active_season.get("title") or "Unknown Season"),
            "archived_key": archived_key,
            "refresh_summary": refresh_summary,
        }


def season_entries_for_render(season: Dict[str, Any]) -> List[Dict[str, Any]]:
    players = season.get("players") or {}
    tracked_order = list(season.get("tracked_uuids") or [])
    banned = load_banned_leaderboard_players()
    entries: List[Dict[str, Any]] = []
    for order_index, player_uuid in enumerate(tracked_order):
        player = players.get(player_uuid)
        if not isinstance(player, dict):
            continue
        tracked_games = int(player.get("tracked_games") or 0)
        if tracked_games < SEASON_MIN_GAMES_VISIBLE:
            continue
        display_name = str(player.get("display_name") or player_uuid[:12]).strip() or player_uuid[:12]
        if display_name.lower() in banned:
            continue
        tracked_wins = int(player.get("tracked_wins") or 0)
        tracked_losses = int(player.get("tracked_losses") or 0)
        wlr = season_player_wlr(tracked_wins, tracked_losses)
        wsr = season_wsr_from_wlr(wlr)
        updated_at = float(player.get("last_update_unix") or season.get("last_refresh_unix") or 0.0)
        entries.append(
            {
                "uuid": player_uuid,
                "order_index": int(player.get("order_index") or order_index),
                "player": display_name,
                "games": tracked_games,
                "wins": tracked_wins,
                "losses": tracked_losses,
                "wlr": wlr,
                "wl": season_wlr_text(wlr),
                "wsr": wsr,
                "updated_at": updated_at,
            }
        )

    entries.sort(key=lambda item: item["wsr"], reverse=True)
    return entries[:LEADERBOARD_MAX_PLAYERS]


def relative_updated_text(updated_at: float) -> str:
    age_seconds = max(0.0, time.time() - float(updated_at or 0.0))
    if updated_at <= 0:
        return "n/a"
    if age_seconds < 3600:
        return "<1h ago"
    if age_seconds < 86400:
        return f"{int(age_seconds // 3600)}h ago"
    return f"{int(age_seconds // 86400)}d ago"


def relative_until_text(target_unix: float) -> str:
    remaining = int(round(float(target_unix or 0.0) - time.time()))
    if remaining <= 0:
        return "due now"
    days, rem = divmod(remaining, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days > 0:
        return f"in {days}d {hours}h"
    if hours > 0:
        return f"in {hours}h {minutes}m"
    if minutes > 0:
        return f"in {minutes}m"
    return "in <1m"


def exact_local_time_text(unix_ts: float) -> str:
    if float(unix_ts or 0.0) <= 0:
        return "n/a"
    local_dt = datetime.fromtimestamp(float(unix_ts)).astimezone()
    offset = local_dt.strftime("%z")
    if len(offset) == 5:
        offset = f"{offset[:3]}:{offset[3:]}"
    tz_label = f"UTC{offset}" if offset else "local"
    return f"{local_dt.strftime('%d %b %Y %H:%M')} {tz_label}"


def season_card_context(season: Dict[str, Any]) -> Dict[str, Any]:
    entries = season_entries_for_render(season)
    rows = [
        {
            "rank": f"#{index}",
            "player": entry["player"],
            "games": f"{entry['games']:,}",
            "wl": entry["wl"],
            "wsr": f"{entry['wsr']:,}",
            "updated": relative_updated_text(entry["updated_at"]),
        }
        for index, entry in enumerate(entries, start=1)
    ]

    top_three = []
    for index in range(3):
        if index < len(entries):
            item = entries[index]
            top_three.append(
                {
                    "rank": index + 1,
                    "player": item["player"],
                    "games": f"{item['games']:,}",
                    "wl": item["wl"],
                    "wsr": f"{item['wsr']:,}",
                }
            )
        else:
            top_three.append({"rank": index + 1, "player": "---", "games": "0", "wl": "0.00", "wsr": "0"})

    next_refresh_unix = float(season.get("next_refresh_unix") or 0.0)
    next_refresh_text = (
        f"{exact_local_time_text(next_refresh_unix)} ({relative_until_text(next_refresh_unix)})"
        if next_refresh_unix > 0
        else "n/a"
    )

    return {
        "season_title": str(season.get("title") or "Season Leaderboard"),
        "rules_text": SEASON_RULES_DESCRIPTION,
        "top_three": top_three,
        "rows": rows,
        "footer_left": "WSR is seasonal and separate from normal SR.",
        "footer_right": "Made by Teishoko",
        "next_refresh_text": next_refresh_text,
        "min_games_visible": SEASON_MIN_GAMES_VISIBLE,
        "tracked_players": len(season.get("tracked_uuids") or []),
        "eligible_players": len(entries),
        "last_refresh": relative_updated_text(float(season.get("last_refresh_unix") or 0.0)),
        "cache_key": f"{season.get('season_key')}::{int(float(season.get('last_refresh_unix') or 0.0))}::{len(rows)}",
    }


def render_season_card_html(season: Dict[str, Any]) -> str:
    context = season_card_context(season)
    return render_custom_template("seasonlb_card.html", **context)

def summary_rows(result: Dict[str, Any]) -> List[Dict[str, str]]:
    return flatten_overall_rows(result)


def favorite_spec(result: Dict[str, Any]) -> str:
    favorite_class = ((result.get("header") or {}).get("favorite_class") or "").strip()
    for class_card in result.get("class_cards") or []:
        if str(class_card.get("label") or "") == favorite_class:
            return str(class_card.get("active_spec_label") or "Unknown")
    return "Unknown"

def extract_spec_sr(value: Any) -> str:
    text = strip_html_tags(value)
    match = re.search(r"SR\s+([0-9,]+|N/A)", text, re.IGNORECASE)
    return match.group(1) if match else "N/A"


def spec_sr_details(value: Any) -> Dict[str, Any]:
    text = strip_html_tags(value)
    match = re.search(r"SR\s+([0-9,]+|N/A)", text, re.IGNORECASE)
    sr_value = match.group(1) if match else "N/A"
    penalty_matches = re.findall(r"\([^)]*SR penalty\)", text, re.IGNORECASE)
    return {
        "value": sr_value,
        "tone": sr_display_tone(sr_value),
        "penalty": len(penalty_matches) > 0,
        "penalty_text": " + ".join(match.strip() for match in penalty_matches),
    }


def side_rows(result: Dict[str, Any], section_key: str) -> List[Dict[str, str]]:
    header = result.get("header") or {}
    return [
        {"label": "Viewing", "value": SECTION_BY_KEY[section_key]["short"], "tone": "tone-cyan"},
        {"label": "Coins", "value": str(header.get("coins") or "0"), "tone": "tone-warn"},
        {"label": "Magic Dust", "value": str(header.get("magic_dust") or "0"), "tone": "tone-cyan"},
        {"label": "Void Shards", "value": str(header.get("void_shards") or "0"), "tone": "tone-pink"},
        {"label": "Overall SR", "value": str(result.get("overall_sr") or "N/A"), "tone": str(result.get("overall_sr_tone") or "tone-white")},
    ]


def hero_blurb(result: Dict[str, Any]) -> str:
    header = result.get("header") or {}
    return player_description(str(header.get("name") or "Unknown"))


def overall_page(result: Dict[str, Any]) -> Dict[str, Any]:
    rows = summary_rows(result)
    return {
        "rows": [
            {
                "left": {
                    "label": left_metric["label"],
                    "value": str(find_row(rows, left_metric["source"]).get("value") or "0"),
                    "tone": str(find_row(rows, left_metric["source"]).get("tone") or left_metric["tone"]),
                },
                "right": {
                    "label": right_metric["label"],
                    "value": str(find_row(rows, right_metric["source"]).get("value") or "0"),
                    "tone": str(find_row(rows, right_metric["source"]).get("tone") or right_metric["tone"]),
                },
            }
            for left_metric, right_metric in OVERALL_STAT_PAIRS
        ]
    }


def class_sr_page(result: Dict[str, Any]) -> Dict[str, Any]:
    classes = []
    for class_card in result.get("class_cards") or []:
        top_rows = class_card.get("top_rows") or []
        metrics = [find_row(top_rows, label) for label in ("Level", "Wins", "Losses", "Played", "W/L", "Win %", "DHP Avg")]
        metrics.append({
            "label": "Spec SR",
            "value": find_row_value(top_rows, "SR", "N/A"),
            "tone": sr_display_tone(find_row_value(top_rows, "SR", "N/A")),
        })
        spec_srs = []
        for spec_row in class_card.get("spec_rows") or []:
            details = spec_sr_details(spec_row.get("value"))
            penalty_text = str(spec_row.get("penalty_text") or details.get("penalty_text") or "").strip()
            spec_srs.append({"label": spec_row.get("label", "Unknown"), **details, "penalty_text": penalty_text, "penalty": bool(penalty_text)})
        classes.append({
            "label": class_card.get("label", "Unknown"),
            "theme": class_card.get("theme", ""),
            "sr": find_row_value(top_rows, "SR", "N/A"),
            "sr_tone": sr_display_tone(find_row_value(top_rows, "SR", "N/A")),
            "metrics": metrics,
            "active_spec": class_card.get("active_spec_label", "Unknown"),
            "spec_srs": spec_srs,
        })
    return {"classes": classes}


def spec_boosts_page(result: Dict[str, Any], allowed_labels: Optional[List[str]] = None) -> Dict[str, Any]:
    boosts = []
    for group in result.get("spec_boost_cards") or []:
        if allowed_labels and str(group.get("label") or "") not in allowed_labels:
            continue
        specs = group.get("specs") or []
        boosts.append({"label": group.get("label", "Unknown"), "theme": group.get("theme", ""), "specs": specs})
    return {"boosts": boosts}


def game_modes_page(result: Dict[str, Any]) -> Dict[str, Any]:
    modes = []
    extra_stats = result.get("extra_stats") or {}
    for row in result.get("mode_rows") or []:
        label = row.get("label", "Unknown")
        if label == "Capture the Flag":
            metrics = [
                {"label": "Wins", "value": row.get("wins", "0"), "tone": "tone-good"},
                {"label": "Flag Captured", "value": extra_stats.get("flag_captured", "0"), "tone": "tone-warn"},
                {"label": "Flag Returned", "value": extra_stats.get("flag_returns", "0"), "tone": "tone-cyan"},
            ]
        elif label == "Domination":
            metrics = [
                {"label": "Wins", "value": row.get("wins", "0"), "tone": "tone-good"},
                {"label": "Captured Points", "value": extra_stats.get("dom_point_captures", "0"), "tone": "tone-cyan"},
                {"label": "Defended Points", "value": extra_stats.get("dom_point_defends", "0"), "tone": "tone-blue"},
            ]
        else:
            metrics = [
                {"label": "Wins", "value": row.get("wins", "0"), "tone": "tone-good"},
                {"label": "Kills", "value": row.get("kills", "0"), "tone": "tone-warn"},
            ]
        modes.append({
            "label": label,
            "metrics": metrics,
            "details": [
                {"label": "Red Wins", "value": row.get("red", "0"), "tone": "tone-bad"},
                {"label": "Blue Wins", "value": row.get("blue", "0"), "tone": "tone-cyan"},
            ],
        })
    return {"modes": modes}


def crafting_page(result: Dict[str, Any]) -> Dict[str, Any]:
    return {"blocks": [{"label": block.get("label", "Unknown"), "theme": block.get("theme", ""), "rows": block.get("rows") or [], "bound_rows": block.get("bound_rows") or []} for block in result.get("crafting_blocks") or []]}


def compact_weapon_rows(card: Dict[str, Any]) -> List[Dict[str, str]]:
    rows = card.get("rows") or []
    return [
        find_row(rows, label)
        for label in (
            "Weapon Score (Approximately)",
            "Damage",
            "Crit Chance",
            "Crit Multiplier",
            "Health",
            "Max Energy",
            "Cooldown Reduction",
            "Speed",
            "Crafted",
            "Void Forged",
        )
    ]


def weapon_inventory_page(result: Dict[str, Any], allowed_labels: Optional[List[str]] = None) -> Dict[str, Any]:
    groups = []
    for group in result.get("weapon_inventory_groups") or []:
        if allowed_labels and str(group.get("label") or "") not in allowed_labels:
            continue
        groups.append({"label": group.get("label", "Unknown"), "theme": group.get("theme", ""), "cards": [{"label": card.get("label", "Unknown"), "title": card.get("title", "Unavailable"), "subtitle": card.get("subtitle", ""), "rows": compact_weapon_rows(card)} for card in group.get("cards") or []]})
    return {"groups": groups}


def chunk_evenly(items: List[Dict[str, str]], columns: int) -> List[List[Dict[str, str]]]:
    if not items:
        return [[] for _ in range(columns)]
    size = math.ceil(len(items) / columns)
    result = [items[index:index + size] for index in range(0, len(items), size)]
    while len(result) < columns:
        result.append([])
    return result


def other_fields_page(result: Dict[str, Any]) -> Dict[str, Any]:
    rows = [row for row in list(result.get("advanced_rows") or []) if str(row.get("label") or "") not in OVERALL_DUPLICATE_LABELS]
    return {"columns": chunk_evenly(rows, 4)}


def build_section_page(result: Dict[str, Any], section_key: str) -> Dict[str, Any]:
    if section_key == "overall_statistics":
        return overall_page(result)
    if section_key == "class_and_sr_breakdown":
        return class_sr_page(result)
    if section_key == "game_mode_breakdown":
        return game_modes_page(result)
    if section_key == "crafting_equipment":
        return crafting_page(result)
    if section_key == "weapon_inv_war_pal":
        return weapon_inventory_page(result, ["Warrior", "Paladin"])
    if section_key == "weapon_inv_mag_sha":
        return weapon_inventory_page(result, ["Mage", "Shaman"])
    if section_key == "spec_boost_war_pal":
        return spec_boosts_page(result, ["Warrior", "Paladin"])
    if section_key == "spec_boost_mag_sha":
        return spec_boosts_page(result, ["Mage", "Shaman"])
    if section_key == "other_tracked_fields":
        return other_fields_page(result)
    raise ValueError(f"Unsupported section: {section_key}")


def render_section_card_html(result: Dict[str, Any], section_key: str) -> str:
    section = SECTION_BY_KEY[section_key]
    header = result.get("header") or {}
    theme = THEME_STYLE[favorite_theme_key(result)]
    return render_custom_template(
        "discord_card.html",
        player_name=header.get("name", "Unknown"),
        player_rank=header.get("rank", "[DEFAULT]"),
        player_rank_segments=header.get("rank_segments") or [{"text": header.get("rank", "[DEFAULT]"), "color": "#f5f8ff"}],
        rank_tone=rank_tone(str(header.get("rank", "[DEFAULT]"))),
        description_title="Description Of The Player",
        player_description=hero_blurb(result),
        active_section_key=section_key,
        side_rows=side_rows(result, section_key),
        sections=SECTION_DEFINITIONS,
        section=section,
        page=build_section_page(result, section_key),
        accent_color=theme["color"],
        accent_soft=theme["soft"],
        footer_left=f"Page {SECTION_INDEX[section_key] + 1}/{len(SECTION_DEFINITIONS)} - Switch sections with the dropdown below.",
        footer_right="Made by Teishoko",
    )


def build_snapshot_embed(result: Dict[str, Any], section_key: str, image_filename: str) -> discord.Embed:
    header = result.get("header") or {}
    rows = summary_rows(result)
    section = SECTION_BY_KEY[section_key]
    embed = discord.Embed(
        title=f"{header.get('rank', '[DEFAULT]')} {header.get('name', 'Unknown')}",
        description=f"Current view: **{section['label']}**",
        color=favorite_class_color(result),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Quick Read", value=trim_text("\n".join([f"Overall SR `{result.get('overall_sr', 'N/A')}`", f"W/L `{find_row_value(rows, 'W/L Ratio')}`", f"K/D `{find_row_value(rows, 'K/D Ratio')}`", f"Win Rate `{find_row_value(rows, 'Win Rate')}`"])), inline=True)
    embed.add_field(name="Navigation", value=trim_text("\n".join(["Use the dropdown for direct jumps.", "Use the arrows for page-by-page browsing.", f"Showing page `{SECTION_INDEX[section_key] + 1}` of `{len(SECTION_DEFINITIONS)}`."])), inline=True)
    embed.set_image(url=f"attachment://{image_filename}")
    embed.set_footer(text=f"{APP_NAME} • interactive section view")
    return embed


def build_embeds(result: Dict[str, Any]) -> List[discord.Embed]:
    header = result.get("header") or {}
    rows = summary_rows(result)
    embed = discord.Embed(title=f"{header.get('rank', '[DEFAULT]')} {header.get('name', 'Unknown')}", description="Fallback Discord view", color=favorite_class_color(result), timestamp=discord.utils.utcnow())
    for label in ("Wins", "Losses", "Games Played", "K/D Ratio", "W/L Ratio", "Win Rate"):
        embed.add_field(name=label, value=find_row_value(rows, label), inline=True)
    embed.add_field(name="Favorite Class", value=str(header.get("favorite_class") or "Unknown"), inline=True)
    embed.add_field(name="Favorite Spec", value=favorite_spec(result), inline=True)
    embed.add_field(name="Overall SR", value=str(result.get("overall_sr") or "N/A"), inline=True)
    embed.set_footer(text="Snapshot renderer unavailable, using fallback view")
    return [embed]


def build_leaderboard_embed(scope_key: str) -> discord.Embed:
    scope = LEADERBOARD_SCOPE_META[scope_key]
    entries = load_leaderboard_cache()
    banned_players = load_banned_leaderboard_players()
    ranked = []
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        result = entry.get("result")
        if not isinstance(result, dict):
            continue
        header = result.get("header") or {}
        username = str(entry.get("username") or header.get("name") or "Unknown")
        if username.strip().lower() in banned_players:
            continue
        score = leaderboard_score(result, scope_key)
        if score is None:
            continue
        ranked.append({
            "username": username,
            "score": score,
            "favorite_class": str(header.get("favorite_class") or "Unknown"),
            "updated_at": float(entry.get("updated_at") or result_updated_at(result) or 0.0),
        })
    ranked.sort(key=lambda item: (-item["score"], str(item["username"]).lower()))
    visible = ranked[:LEADERBOARD_MAX_PLAYERS]

    theme = THEME_COLORS.get(scope["theme"], discord.Color.blurple())
    embed = discord.Embed(
        title=f"{scope['label']} Leaderboard",
        description="Tracked players only. Results refresh when a saved player is older than 1 day and gets searched again.",
        color=theme,
        timestamp=discord.utils.utcnow(),
    )
    if not visible:
        embed.add_field(
            name="No tracked players yet",
            value="Use `/sr <player>` to save players into the leaderboard pool first.",
            inline=False,
        )
        embed.set_footer(text="Top 25 max")
        return embed

    lines = []
    for index, item in enumerate(visible, start=1):
        medal = "🥇 " if index == 1 else "🥈 " if index == 2 else "🥉 " if index == 3 else ""
        lines.append(f"{medal}`#{index:02}` **{item['username']}** - `{item['score']:,}`")

    embed.add_field(name="Rankings", value="\n".join(lines), inline=False)
    embed.set_footer(text=f"Showing top {len(visible)} of {len(ranked)} tracked players")
    return embed


def build_leaderboard_rows(scope_key: str, subsection_key: str = "overall") -> Dict[str, Any]:
    entries = load_leaderboard_cache()
    banned_players = load_banned_leaderboard_players()
    allowed_entries = []
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        result = entry.get("result")
        if not isinstance(result, dict):
            continue
        header = result.get("header") or {}
        username = str(entry.get("username") or header.get("name") or "Unknown")
        if username.strip().lower() in banned_players:
            continue
        allowed_entries.append({
            "username": username,
            "favorite_class": str(header.get("favorite_class") or "Unknown"),
            "updated_at": float(entry.get("updated_at") or result_updated_at(result) or 0.0),
            "result": result,
        })

    if scope_key == "overall" or subsection_key == "overall":
        ranked = []
        for entry in allowed_entries:
            score = leaderboard_score(entry["result"], scope_key)
            if score is None:
                continue
            ranked.append({
                "username": entry["username"],
                "score": score,
                "favorite_class": entry["favorite_class"],
                "updated_at": entry["updated_at"],
            })
        ranked.sort(key=lambda item: (-item["score"], str(item["username"]).lower()))
        visible = ranked[:LEADERBOARD_MAX_PLAYERS]
        return {"mode": "ladder", "visible": visible, "tracked_total": len(ranked)}

    spec_label = subsection_key
    ranked = []
    for entry in allowed_entries:
        score = spec_leaderboard_score(entry["result"], spec_label)
        if score is None:
            continue
        ranked.append({
            "username": entry["username"],
            "score": score,
            "favorite_class": entry["favorite_class"],
            "updated_at": entry["updated_at"],
        })
    ranked.sort(key=lambda item: (-item["score"], str(item["username"]).lower()))
    visible = ranked[:LEADERBOARD_MAX_PLAYERS]
    return {
        "mode": "ladder",
        "visible": visible,
        "tracked_total": len(ranked),
        "spec_label": spec_label,
    }


def spec_leaderboard_score(result: Dict[str, Any], spec_label: str) -> Optional[int]:
    target = spec_label.strip().lower()
    for class_card in result.get("class_cards") or []:
        for spec_row in class_card.get("spec_rows") or []:
            if str(spec_row.get("label") or "").strip().lower() != target:
                continue
            details = spec_sr_details(spec_row.get("value"))
            value = str(details.get("value") or "").replace(",", "").strip().upper()
            return int(value) if value.isdigit() else None
    return None


def leaderboard_sections(scope_key: str) -> List[Dict[str, str]]:
    if scope_key == "overall":
        return [{"key": "overall", "label": "Overall SR", "short": "Overall"}]
    base_label = LEADERBOARD_SCOPE_META[scope_key]["label"]
    return [{"key": "overall", "label": base_label, "short": "Overall"}] + [
        {"key": spec_label, "label": f"{spec_label} SR", "short": f"{spec_label} SR"}
        for spec_label in LEADERBOARD_SCOPE_SPECS[scope_key]
    ]


def leaderboard_card_context(scope_key: str, subsection_key: str = "overall") -> Dict[str, Any]:
    scope = LEADERBOARD_SCOPE_META[scope_key]
    section_items = leaderboard_sections(scope_key)
    description_text = (
        LEADERBOARD_OVERALL_DESCRIPTION
        if scope_key == "overall"
        else LEADERBOARD_CLASS_DESCRIPTION if subsection_key == "overall"
        else LEADERBOARD_SPEC_DESCRIPTION
    )
    rows_data = build_leaderboard_rows(scope_key, subsection_key)
    tracked_total = rows_data["tracked_total"]
    now = time.time()
    visible = rows_data["visible"]
    table_rows = []
    for index, item in enumerate(visible, start=1):
        age_seconds = max(0, now - item["updated_at"]) if item["updated_at"] else 0
        if age_seconds < 3600:
            updated = "<1h ago"
        elif age_seconds < 86400:
            updated = f"{int(age_seconds // 3600)}h ago"
        else:
            updated = f"{int(age_seconds // 86400)}d ago"
        table_rows.append({
            "rank": f"#{index}",
            "player": item["username"],
            "score": f"{item['score']:,}",
            "class": item["favorite_class"],
            "updated": updated,
            "tone": sr_display_tone(str(item["score"])),
        })
    label = scope["label"] if subsection_key == "overall" else f"{subsection_key} SR"
    page: Dict[str, Any] = {
        "mode": "ladder",
        "rows": table_rows,
        "tracked_total": tracked_total,
        "max_players": LEADERBOARD_MAX_PLAYERS,
        "theme": scope["theme"],
    }
    return {
        "scope_key": scope_key,
        "subsection_key": subsection_key,
        "section": {
            "key": "leaderboard",
            "label": f"{label} Leaderboard",
            "short": "Leaderboard",
            "kicker": "Tracked Rankings",
            "note": "",
        },
        "player_name": "Tracked Pool",
        "player_rank_segments": [{"text": "[LB]", "color": THEME_STYLE[scope["theme"]]["color"]}],
        "description_title": "How does the leaderboard work?",
        "player_description": description_text,
        "active_section_key": subsection_key,
        "side_rows": [
            {"label": "Viewing", "value": label, "tone": "tone-cyan"},
            {"label": "Tracked Players", "value": str(tracked_total), "tone": "tone-white"},
            {"label": "Visible Slots", "value": f"Top {LEADERBOARD_MAX_PLAYERS}", "tone": "tone-warn"},
            {"label": "Refresh Rule", "value": "1 day", "tone": "tone-cyan"},
            {"label": "Layout", "value": "Dropdown pages" if scope_key != "overall" else "1 ladder", "tone": "tone-pink"},
        ],
        "sections": section_items,
        "page": page,
        "footer_left": "Tracked-player leaderboard. Search players with /sr to add or refresh them.",
        "footer_right": "Made by Teishoko",
        "accent_color": THEME_STYLE[scope["theme"]]["color"],
        "accent_soft": THEME_STYLE[scope["theme"]]["soft"],
    }


def render_leaderboard_card_html(scope_key: str, subsection_key: str = "overall") -> str:
    context = leaderboard_card_context(scope_key, subsection_key)
    return render_custom_template("discord_card.html", **context)


async def leaderboard_snapshot(scope_key: str, subsection_key: str = "overall") -> Tuple[bytes, str]:
    html = render_leaderboard_card_html(scope_key, subsection_key)
    return await snapshot_renderer.render_html(html)


class SnapshotRenderer:
    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if async_playwright is None:
            raise RuntimeError("Playwright is not installed.")
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch()

    async def stop(self) -> None:
        async with self._lock:
            await self._shutdown_unlocked()

    async def _shutdown_unlocked(self) -> None:
        if self._browser is not None:
            with contextlib.suppress(Exception):
                await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            with contextlib.suppress(Exception):
                await self._playwright.stop()
            self._playwright = None

    async def render_html(self, html: str, selector: str = CARD_SELECTOR) -> Tuple[bytes, str]:
        async with self._lock:
            if self._browser is None:
                await self.start()
            page = None
            try:
                page = await self._browser.new_page(viewport={"width": 1680, "height": 1480}, device_scale_factor=1.2)
                await page.set_content(html, wait_until="load")
                await page.emulate_media(color_scheme="dark")
                locator = page.locator(selector)
                await locator.wait_for(state="visible")
                await page.wait_for_timeout(100)
                png_bytes = await locator.screenshot(type="png")
                if len(png_bytes) <= MAX_DISCORD_ATTACHMENT_BYTES:
                    return png_bytes, "png"
                return await locator.screenshot(type="jpeg", quality=88), "jpg"
            except PlaywrightError as exc:
                await self._shutdown_unlocked()
                raise RuntimeError("Failed to render the Discord card.") from exc
            finally:
                if page is not None:
                    with contextlib.suppress(Exception):
                        await page.close()


snapshot_renderer = SnapshotRenderer()


async def cached_section_snapshot(username: str, result: Dict[str, Any], section_key: str) -> Tuple[bytes, str]:
    key = f"{validate_username(username).lower()}::{section_key}"
    now = time.time()
    with SECTION_IMAGE_CACHE_LOCK:
        cached = SECTION_IMAGE_CACHE.get(key)
        if cached and now - cached[0] <= SECTION_CACHE_TTL_SECONDS:
            return cached[1], cached[2]
    html = render_section_card_html(result, section_key)
    image_bytes, extension = await snapshot_renderer.render_html(html)
    with SECTION_IMAGE_CACHE_LOCK:
        SECTION_IMAGE_CACHE[key] = (time.time(), image_bytes, extension)
    return image_bytes, extension


async def cached_leaderboard_snapshot(scope_key: str, subsection_key: str) -> Tuple[bytes, str]:
    key = f"leaderboard::{scope_key}::{subsection_key}"
    now = time.time()
    with SECTION_IMAGE_CACHE_LOCK:
        cached = SECTION_IMAGE_CACHE.get(key)
        if cached and now - cached[0] <= SECTION_CACHE_TTL_SECONDS:
            return cached[1], cached[2]
    image_bytes, extension = await leaderboard_snapshot(scope_key, subsection_key)
    with SECTION_IMAGE_CACHE_LOCK:
        SECTION_IMAGE_CACHE[key] = (time.time(), image_bytes, extension)
    return image_bytes, extension


def active_season_record() -> Optional[Dict[str, Any]]:
    with SEASON_STATE_LOCK:
        state = load_season_state()
        active_key = str(state.get("active_season_key") or "")
        season = (state.get("seasons") or {}).get(active_key)
        return json.loads(json.dumps(season)) if isinstance(season, dict) else None


async def seasonlb_snapshot() -> Tuple[bytes, str]:
    season = active_season_record()
    if not season:
        raise RuntimeError("No active season state available.")
    html = render_season_card_html(season)
    return await snapshot_renderer.render_html(html, selector="#season-card")


async def cached_seasonlb_snapshot() -> Tuple[bytes, str]:
    season = active_season_record()
    if not season:
        raise RuntimeError("No active season state available.")
    cache_key = season_card_context(season)["cache_key"]
    key = f"seasonlb::{cache_key}"
    now = time.time()
    with SECTION_IMAGE_CACHE_LOCK:
        cached = SECTION_IMAGE_CACHE.get(key)
        if cached and now - cached[0] <= SECTION_CACHE_TTL_SECONDS:
            return cached[1], cached[2]
    image_bytes, extension = await seasonlb_snapshot()
    with SECTION_IMAGE_CACHE_LOCK:
        SECTION_IMAGE_CACHE[key] = (time.time(), image_bytes, extension)
    return image_bytes, extension


def season_archive_candidates() -> List[Dict[str, Any]]:
    with SEASON_STATE_LOCK:
        state = load_season_state()
        candidates: List[Dict[str, Any]] = []
        for season in (state.get("seasons") or {}).values():
            if not isinstance(season, dict):
                continue
            if str(season.get("archive_status") or "") != "pending":
                continue
            candidates.append(json.loads(json.dumps(season)))
        return candidates


def mark_season_archive_result(season_key: str, success: bool, archive_filename: str, error: str = "") -> None:
    with SEASON_STATE_LOCK:
        state = load_season_state()
        season = (state.get("seasons") or {}).get(season_key)
        if not isinstance(season, dict):
            return
        if success:
            season["archive_status"] = "done"
            season["archived_unix"] = datetime.now().astimezone().timestamp()
            season["archive_filename"] = archive_filename
            season["archive_error"] = ""
        else:
            season["archive_status"] = "pending"
            season["archive_error"] = error
        save_season_state(state)


async def archive_pending_seasons() -> None:
    candidates = season_archive_candidates()
    if not candidates:
        return
    OLD_SEASONS_DIR.mkdir(parents=True, exist_ok=True)
    for season in candidates:
        season_key = str(season.get("season_key") or "")
        if not season_key:
            continue
        try:
            html = render_season_card_html(season)
            image_bytes, extension = await snapshot_renderer.render_html(html, selector="#season-card")
            base_name = str(season.get("archive_filename") or "").strip()
            if not base_name:
                base_name = f"{sanitize_filename(str(season.get('title') or season_key)).lower()}.{extension}"
            if not base_name.lower().endswith(f".{extension}"):
                base_name = f"{Path(base_name).stem}.{extension}"
            archive_path = OLD_SEASONS_DIR / base_name
            archive_path.write_bytes(image_bytes)
            mark_season_archive_result(season_key, True, base_name)
        except Exception as exc:
            logging.exception("Failed to archive finished season %s", season_key)
            mark_season_archive_result(season_key, False, str(season.get("archive_filename") or ""), error=str(exc))


async def run_season_maintenance(force_refresh: bool = False, refresh_stats: bool = True) -> Dict[str, Any]:
    summary = await asyncio.to_thread(update_season_state, force_refresh, refresh_stats)
    await archive_pending_seasons()
    return summary


def refresh_seasonlb_now(force: bool = True) -> Dict[str, Any]:
    return update_season_state(force_refresh=force, refresh_stats=True)


class SectionSelect(discord.ui.Select):
    def __init__(self, owner: "WarlordsSectionView") -> None:
        self.owner = owner
        options = [discord.SelectOption(label=section["label"], value=section["key"], description=section["short"], default=section["key"] == owner.current_section_key) for section in SECTION_DEFINITIONS]
        super().__init__(placeholder=SECTION_BY_KEY[owner.current_section_key]["label"], min_values=1, max_values=1, options=options, row=0)

    def sync(self) -> None:
        self.placeholder = SECTION_BY_KEY[self.owner.current_section_key]["label"]
        for option in self.options:
            option.default = option.value == self.owner.current_section_key

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.owner.change_section(interaction, self.values[0])


class WarlordsSectionView(discord.ui.View):
    def __init__(self, username: str, result: Dict[str, Any]) -> None:
        super().__init__(timeout=1800)
        self.username = username
        self.result = result
        self.current_section_key = SECTION_DEFINITIONS[0]["key"]
        self.message: Optional[discord.Message] = None
        self._render_lock = asyncio.Lock()
        self.select_menu = SectionSelect(self)
        self.add_item(self.select_menu)
        self.select_menu.sync()

    def sync_controls(self) -> None:
        self.select_menu.sync()

    async def build_message_payload(self) -> discord.File:
        image_bytes, extension = await cached_section_snapshot(self.username, self.result, self.current_section_key)
        name = (self.result.get("header") or {}).get("name") or self.username
        filename = f"{sanitize_filename(name)}-{self.current_section_key}.{extension}"
        return discord.File(io.BytesIO(image_bytes), filename=filename)

    async def refresh_message(self, interaction: discord.Interaction) -> None:
        async with self._render_lock:
            await interaction.response.defer()
            file = await self.build_message_payload()
            self.sync_controls()
            await interaction.edit_original_response(attachments=[file], view=self)

    async def change_section(self, interaction: discord.Interaction, section_key: str) -> None:
        if section_key not in SECTION_BY_KEY:
            return
        self.current_section_key = section_key
        await self.refresh_message(interaction)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            with contextlib.suppress(Exception):
                await self.message.edit(view=self)


class LeaderboardSelect(discord.ui.Select):
    def __init__(self, owner: "LeaderboardSectionView") -> None:
        self.owner = owner
        options = [
            discord.SelectOption(
                label=section["label"],
                value=section["key"],
                description=section["short"],
                default=section["key"] == owner.current_subsection_key,
            )
            for section in leaderboard_sections(owner.scope_key)
        ]
        placeholder = next(
            (section["label"] for section in leaderboard_sections(owner.scope_key) if section["key"] == owner.current_subsection_key),
            "Leaderboard",
        )
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, row=0)

    def sync(self) -> None:
        sections = leaderboard_sections(self.owner.scope_key)
        self.placeholder = next(
            (section["label"] for section in sections if section["key"] == self.owner.current_subsection_key),
            "Leaderboard",
        )
        for option in self.options:
            option.default = option.value == self.owner.current_subsection_key

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.owner.change_section(interaction, self.values[0])


class LeaderboardSectionView(discord.ui.View):
    def __init__(self, scope_key: str) -> None:
        super().__init__(timeout=1800)
        self.scope_key = scope_key
        self.current_subsection_key = "overall"
        self.message: Optional[discord.Message] = None
        self._render_lock = asyncio.Lock()
        self.select_menu = LeaderboardSelect(self)
        self.add_item(self.select_menu)
        self.select_menu.sync()

    def sync_controls(self) -> None:
        self.select_menu.sync()

    async def build_message_payload(self) -> discord.File:
        image_bytes, extension = await cached_leaderboard_snapshot(self.scope_key, self.current_subsection_key)
        filename = f"leaderboard-{self.scope_key}-{sanitize_filename(self.current_subsection_key)}.{extension}"
        return discord.File(io.BytesIO(image_bytes), filename=filename)

    async def refresh_message(self, interaction: discord.Interaction) -> None:
        async with self._render_lock:
            await interaction.response.defer()
            file = await self.build_message_payload()
            self.sync_controls()
            await interaction.edit_original_response(attachments=[file], view=self)

    async def change_section(self, interaction: discord.Interaction, subsection_key: str) -> None:
        valid_keys = {section["key"] for section in leaderboard_sections(self.scope_key)}
        if subsection_key not in valid_keys:
            return
        self.current_subsection_key = subsection_key
        await self.refresh_message(interaction)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            with contextlib.suppress(Exception):
                await self.message.edit(view=self)


class WarlordsBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default(), help_command=None)
        self._season_task: Optional[asyncio.Task] = None

    async def setup_hook(self) -> None:
        if async_playwright is not None:
            try:
                await snapshot_renderer.start()
                logging.info("Snapshot renderer ready")
            except Exception:
                logging.exception("Snapshot renderer could not start. The bot will fall back to embeds.")
        else:
            logging.warning("Playwright is unavailable. The bot will fall back to embeds.")
        if self._season_task is None:
            self._season_task = asyncio.create_task(self._season_scheduler_loop(), name="seasonlb-refresh-loop")
        guild_id = os.environ.get("DISCORD_GUILD_ID", "").strip()
        if guild_id:
            try:
                guild = discord.Object(id=int(guild_id))
            except ValueError:
                logging.warning("Ignoring invalid DISCORD_GUILD_ID value: %s", guild_id)
            else:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logging.info("Synced %s guild slash command(s) to guild %s", len(synced), guild_id)
                return
        synced = await self.tree.sync()
        logging.info("Synced %s global slash command(s)", len(synced))

    async def close(self) -> None:
        if self._season_task is not None:
            self._season_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._season_task
            self._season_task = None
        await snapshot_renderer.stop()
        await super().close()

    async def on_ready(self) -> None:
        activity = discord.Activity(type=discord.ActivityType.watching, name=os.environ.get("DISCORD_STATUS_TEXT", "/warlords"))
        await self.change_presence(activity=activity)
        logging.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")

    async def _season_scheduler_loop(self) -> None:
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                summary = await run_season_maintenance(force_refresh=False, refresh_stats=True)
                refresh_info = summary.get("refresh_summary") or {}
                if refresh_info.get("performed"):
                    logging.info(
                        "SeasonLB refresh complete | season=%s tracked=%s eligible=%s changed_games=%s errors=%s",
                        summary.get("active_season_title"),
                        refresh_info.get("tracked_count"),
                        refresh_info.get("eligible_count"),
                        refresh_info.get("changed_games"),
                        refresh_info.get("error_count"),
                    )
            except Exception:
                logging.exception("SeasonLB scheduler loop iteration failed.")
            await asyncio.sleep(60)


bot = WarlordsBot()
lb_group = app_commands.Group(name="lb", description="Show tracked SR leaderboards")


async def send_leaderboard(interaction: discord.Interaction, scope_key: str) -> None:
    await interaction.response.defer(thinking=True)
    try:
        if scope_key == "overall":
            image_bytes, extension = await cached_leaderboard_snapshot(scope_key, "overall")
            filename = f"leaderboard-{scope_key}.{extension}"
            file = discord.File(io.BytesIO(image_bytes), filename=filename)
            await interaction.followup.send(file=file)
        else:
            view = LeaderboardSectionView(scope_key)
            file = await view.build_message_payload()
            message = await interaction.followup.send(file=file, view=view, wait=True)
            view.message = message
    except Exception:
        logging.exception("Leaderboard card render failed for %s", scope_key)
        embed = await asyncio.to_thread(build_leaderboard_embed, scope_key)
        await interaction.followup.send(
            content="The leaderboard card failed to render, so here is the fallback Discord view.",
            embed=embed,
        )


@lb_group.command(name="overall", description="Show the tracked Overall SR leaderboard")
async def lb_overall(interaction: discord.Interaction) -> None:
    await send_leaderboard(interaction, "overall")


@lb_group.command(name="mage", description="Show the tracked Mage SR leaderboard")
async def lb_mage(interaction: discord.Interaction) -> None:
    await send_leaderboard(interaction, "mage")


@lb_group.command(name="warrior", description="Show the tracked Warrior SR leaderboard")
async def lb_warrior(interaction: discord.Interaction) -> None:
    await send_leaderboard(interaction, "warrior")


@lb_group.command(name="paladin", description="Show the tracked Paladin SR leaderboard")
async def lb_paladin(interaction: discord.Interaction) -> None:
    await send_leaderboard(interaction, "paladin")


@lb_group.command(name="shaman", description="Show the tracked Shaman SR leaderboard")
async def lb_shaman(interaction: discord.Interaction) -> None:
    await send_leaderboard(interaction, "shaman")


bot.tree.add_command(lb_group)


def build_seasonlb_fallback_embed() -> discord.Embed:
    season = active_season_record() or {}
    context = season_card_context(season) if season else {}
    embed = discord.Embed(
        title=str(context.get("season_title") or "Seasonal WSR Leaderboard"),
        description="Image renderer failed, so here is the fallback summary.",
        color=discord.Color.from_rgb(255, 95, 118),
        timestamp=discord.utils.utcnow(),
    )
    rows = context.get("rows") or []
    if not rows:
        embed.add_field(
            name="No eligible players yet",
            value=f"Players appear after {SEASON_MIN_GAMES_VISIBLE} tracked games.",
            inline=False,
        )
    else:
        lines = []
        for row in rows[:LEADERBOARD_MAX_PLAYERS]:
            lines.append(
                f"{row['rank']} **{row['player']}** | WSR `{row['wsr']}` | W/L `{row['wl']}` | Games `{row['games']}`"
            )
        embed.add_field(name="Top Seasonal WSR", value="\n".join(lines), inline=False)
    next_refresh_text = context.get("next_refresh_text") or "n/a"
    embed.add_field(name="Next Refresh", value=str(next_refresh_text), inline=False)
    embed.set_footer(text="SeasonLB fallback view")
    return embed


@bot.tree.command(name="seasonlb", description="Show the seasonal WSR leaderboard")
async def seasonlb(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    try:
        await run_season_maintenance(force_refresh=False, refresh_stats=False)
        image_bytes, extension = await cached_seasonlb_snapshot()
        filename = f"seasonlb.{extension}"
        file = discord.File(io.BytesIO(image_bytes), filename=filename)
        await interaction.followup.send(file=file)
    except Exception:
        logging.exception("SeasonLB render failed")
        await interaction.followup.send(
            content="The seasonal leaderboard image failed to render, so here is the fallback text view.",
            embed=build_seasonlb_fallback_embed(),
        )


@bot.tree.command(name="sr", description="Check a player's Hypixel Warlords stats")
@app_commands.describe(player="Minecraft username")
async def sr(interaction: discord.Interaction, player: str) -> None:
    await interaction.response.defer(thinking=True)
    try:
        async with LOOKUP_SEMAPHORE:
            result = await asyncio.to_thread(cached_lookup, player)
    except ValueError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return
    except Exception:
        logging.exception("Unexpected error while looking up %s", player)
        await interaction.followup.send("Something went wrong while contacting Mojang or Hypixel. Please try again in a moment.", ephemeral=True)
        return
    view = WarlordsSectionView(player, result)
    try:
        file = await view.build_message_payload()
        message = await interaction.followup.send(file=file, view=view, wait=True)
        view.message = message
    except Exception:
        logging.exception("Interactive card render failed for %s", player)
        await interaction.followup.send(content="The interactive card failed to render, so here is the fallback Discord view.", embeds=build_embeds(result))

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    logging.exception("Unhandled app command error", exc_info=error)
    if interaction.response.is_done():
        await interaction.followup.send("The command failed unexpectedly. Please try again.", ephemeral=True)
    else:
        await interaction.response.send_message("The command failed unexpectedly. Please try again.", ephemeral=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    load_env_file()
    token = load_discord_token()
    if not token:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN in .env.")
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
