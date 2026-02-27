"""Import HBS BattleTech mech definitions into canonical format.

Usage:
    python -m importers.hbs_importer --hbs-data ../BattleTech/data --output data/mechs

Reads mechdef_*.json and chassisdef_*.json from HBS data directory,
converts them to our canonical per-mech JSON format, and writes individual
files to the output directory.
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to path so we can import battletech
sys.path.insert(0, str(Path(__file__).parent.parent))

from battletech.weapons import WEAPON_DB
from importers.weapon_map import map_weapon, AMMO_MAP, ammo_matches_weapon
from importers.chassis_stats import WALK_MP


# HBS location names -> our 2-letter location IDs
HBS_LOCATION_MAP = {
    "Head":        "HD",
    "CenterTorso": "CT",
    "LeftTorso":   "LT",
    "RightTorso":  "RT",
    "LeftArm":     "LA",
    "RightArm":    "RA",
    "LeftLeg":     "LL",
    "RightLeg":    "RL",
}

# All 8 standard locations in canonical order
LOCATION_ORDER = ["HD", "CT", "LT", "RT", "LA", "RA", "LL", "RL"]

# Locations with rear armor
REAR_LOCATIONS = {"CT", "LT", "RT"}

# Default armor divisor: HBS armor / divisor ≈ TT armor
DEFAULT_ARMOR_DIVISOR = 5


def load_json(filepath: Path) -> dict:
    """Load a JSON file, handling trailing commas and encoding issues.

    HBS JSON files sometimes have trailing commas before ] or } which
    is non-standard. We strip those before parsing.
    """
    import re
    with open(filepath, encoding="utf-8-sig") as f:
        text = f.read()
    # Remove trailing commas before ] or }
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def is_blacklisted(mechdef: dict) -> bool:
    """Check if a mechdef is blacklisted, a template, or a test dummy."""
    tags = mechdef.get("MechTags", {}).get("items", [])
    if "BLACKLISTED" in tags:
        return True
    desc = mechdef.get("Description", {})
    name = desc.get("UIName", "") or desc.get("Name", "") or ""
    if not name or "TARGETDUMMY" in name.upper() or "TESTDUMMY" in name.upper():
        return True
    return False


def load_chassis(chassis_dir: Path, chassis_id: str) -> dict | None:
    """Load a chassis definition by its ChassisID."""
    filename = f"{chassis_id}.json"
    filepath = chassis_dir / filename
    if filepath.exists():
        return load_json(filepath)
    return None


def convert_armor(hbs_armor: int, divisor: float) -> int:
    """Convert HBS armor value to approximate TT armor."""
    if hbs_armor <= 0:
        return 0
    return max(1, round(hbs_armor / divisor))


def import_mech(mechdef: dict, chassis: dict, armor_divisor: float) -> dict | None:
    """Convert an HBS mechdef + chassis into our canonical mech format.

    Returns None if the mech can't be imported (missing walk_mp, etc.).
    """
    desc = mechdef.get("Description", {})
    ui_name = desc.get("UIName", "")
    chassis_desc = chassis.get("Description", {})

    variant_name = chassis.get("VariantName", "")
    tonnage = chassis["Tonnage"]
    weight_class = chassis.get("weightClass", "MEDIUM").lower()
    stock_role = chassis.get("StockRole", "")

    # Look up TT walk_mp from our table
    if variant_name not in WALK_MP:
        print(f"  WARNING: No walk_mp for variant '{variant_name}' ({ui_name}) — skipping")
        return None
    walk_mp = WALK_MP[variant_name]
    run_mp = int(walk_mp * 1.5 + 0.5)

    # Count jump jets from inventory
    jump_mp = sum(
        1 for item in mechdef.get("inventory", [])
        if item.get("ComponentDefType") == "JumpJet"
    )

    # Count heat sinks from inventory (10 base + inventory count)
    hs_count = sum(
        1 for item in mechdef.get("inventory", [])
        if item.get("ComponentDefType") == "HeatSink"
    )
    total_heat_sinks = 10 + hs_count

    # Detect double heat sinks
    double_hs = any(
        "Double" in item.get("ComponentDefID", "")
        for item in mechdef.get("inventory", [])
        if item.get("ComponentDefType") == "HeatSink"
    )

    # Build locations with converted armor
    hbs_locations = {loc["Location"]: loc for loc in mechdef.get("Locations", [])}
    locations = []
    for hbs_name, loc_id in HBS_LOCATION_MAP.items():
        hbs_loc = hbs_locations.get(hbs_name, {})
        front_armor = convert_armor(hbs_loc.get("CurrentArmor", 0), armor_divisor)
        rear_armor = 0
        if loc_id in REAR_LOCATIONS:
            hbs_rear = hbs_loc.get("CurrentRearArmor", -1)
            if hbs_rear > 0:
                rear_armor = convert_armor(hbs_rear, armor_divisor)

        loc_dict = {"name": loc_id, "armor": front_armor}
        if rear_armor > 0:
            loc_dict["rear_armor"] = rear_armor
        loc_dict["crittable_slots"] = []  # populated below
        locations.append(loc_dict)

    # Build a lookup for quick access
    loc_by_id = {loc["name"]: loc for loc in locations}

    # Always add Engine×3 to CT
    loc_by_id["CT"]["crittable_slots"] = ["Engine", "Engine", "Engine"]

    # Map weapons from inventory
    weapons = []
    skipped_weapons = []
    for item in mechdef.get("inventory", []):
        if item.get("ComponentDefType") != "Weapon":
            continue
        comp_id = item["ComponentDefID"]
        hbs_loc = item["MountedLocation"]
        loc_id = HBS_LOCATION_MAP.get(hbs_loc)
        if not loc_id:
            continue

        weapon_name = map_weapon(comp_id)
        if weapon_name is None:
            skipped_weapons.append(comp_id)
            continue

        weapons.append({
            "name": weapon_name,
            "location": loc_id,
            # ammo will be filled in below
        })

        # Add to crittable slots
        loc_by_id[loc_id]["crittable_slots"].append(weapon_name)

    if skipped_weapons:
        unique_skipped = sorted(set(skipped_weapons))
        print(f"  WARNING: Skipped unmapped weapons in {ui_name}: {unique_skipped}")

    # Count ammo boxes per type per location
    ammo_tons: dict[str, int] = defaultdict(int)  # ammo_family -> total tons
    ammo_locations: dict[str, list[str]] = defaultdict(list)  # ammo_family -> [loc_ids]
    for item in mechdef.get("inventory", []):
        if item.get("ComponentDefType") != "AmmunitionBox":
            continue
        comp_id = item["ComponentDefID"]
        hbs_loc = item["MountedLocation"]
        loc_id = HBS_LOCATION_MAP.get(hbs_loc)
        if not loc_id:
            continue

        ammo_family = AMMO_MAP.get(comp_id)
        if ammo_family is None:
            continue  # Unsupported ammo type (e.g., Gauss)

        ammo_tons[ammo_family] += 1
        ammo_locations[ammo_family].append(loc_id)

        # Add ammo to crittable slots
        # Find the weapon name to build the "Ammo X" slot name
        for w in weapons:
            if ammo_matches_weapon(ammo_family, w["name"]):
                loc_by_id[loc_id]["crittable_slots"].append(f"Ammo {w['name']}")
                break

    # Distribute ammo to weapons
    for ammo_family, tons in ammo_tons.items():
        # Find all weapons that use this ammo family
        matching_weapons = [
            w for w in weapons
            if ammo_matches_weapon(ammo_family, w["name"])
        ]
        if not matching_weapons:
            continue

        # Look up ammo_per_ton from WEAPON_DB
        weapon_ref = WEAPON_DB.get(matching_weapons[0]["name"])
        if not weapon_ref or weapon_ref.ammo_per_ton is None:
            continue

        total_rounds = tons * weapon_ref.ammo_per_ton
        rounds_per_weapon = total_rounds // len(matching_weapons)
        remainder = total_rounds % len(matching_weapons)

        for i, w in enumerate(matching_weapons):
            w["ammo"] = rounds_per_weapon + (1 if i < remainder else 0)

    # Clean up: remove empty crittable_slots lists from locations
    for loc in locations:
        if not loc["crittable_slots"]:
            loc["crittable_slots"] = []

    # Build the canonical mech dict
    mech_dict = {
        "name": ui_name,
        "tonnage": tonnage,
        "walk_mp": walk_mp,
        "run_mp": run_mp,
        "jump_mp": jump_mp,
        "gunnery": 4,
        "piloting": 5,
        "heat_sinks": total_heat_sinks,
        "double_heat_sinks": double_hs,
        "engine_type": "standard",
        "locations": locations,
        "weapons": weapons,
        "metadata": {
            "source": "hbs",
            "bv2": None,
            "cost_cbills": desc.get("Cost"),
            "tech_base": "Inner Sphere",
            "year_introduced": None,
            "era": None,
            "role": stock_role or None,
            "weight_class": weight_class,
        },
    }

    return mech_dict


def make_filename(ui_name: str) -> str:
    """Convert a mech UIName to a filename.

    'Atlas AS7-D' -> 'atlas_AS7-D.json'
    'Shadow Hawk SHD-2H' -> 'shadow_hawk_SHD-2H.json'
    """
    parts = ui_name.rsplit(" ", 1)
    if len(parts) == 2:
        chassis_name, variant = parts
        chassis_slug = chassis_name.lower().replace(" ", "_")
        return f"{chassis_slug}_{variant}.json"
    return ui_name.lower().replace(" ", "_") + ".json"


def main():
    parser = argparse.ArgumentParser(description="Import HBS BattleTech mechs")
    parser.add_argument("--hbs-data", required=True,
                        help="Path to HBS BattleTech data/ directory")
    parser.add_argument("--output", default="data/mechs",
                        help="Output directory for mech JSONs")
    parser.add_argument("--armor-divisor", type=float, default=DEFAULT_ARMOR_DIVISOR,
                        help=f"HBS armor / divisor = TT armor (default: {DEFAULT_ARMOR_DIVISOR})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and validate but don't write files")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing files (default: skip)")
    args = parser.parse_args()

    hbs_data = Path(args.hbs_data)
    mech_dir = hbs_data / "mech"
    chassis_dir = hbs_data / "chassis"
    output_dir = Path(args.output)

    if not output_dir.is_absolute():
        output_dir = Path(__file__).parent.parent / output_dir

    if not mech_dir.exists():
        print(f"Error: HBS mech directory not found: {mech_dir}")
        sys.exit(1)
    if not chassis_dir.exists():
        print(f"Error: HBS chassis directory not found: {chassis_dir}")
        sys.exit(1)

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Find all mechdef files
    mechdef_files = sorted(mech_dir.glob("mechdef_*.json"))
    print(f"Found {len(mechdef_files)} mechdef files")

    imported = 0
    skipped_blacklisted = 0
    skipped_no_chassis = 0
    skipped_no_walkmp = 0
    skipped_no_weapons = 0
    skipped_existing = 0

    for mf in mechdef_files:
        mechdef = load_json(mf)

        # Skip blacklisted/test mechs
        if is_blacklisted(mechdef):
            skipped_blacklisted += 1
            continue

        ui_name = mechdef.get("Description", {}).get("UIName", mf.stem)
        chassis_id = mechdef.get("ChassisID", "")

        # Load chassis
        chassis = load_chassis(chassis_dir, chassis_id)
        if chassis is None:
            print(f"  WARNING: Chassis not found for {ui_name} ({chassis_id}) — skipping")
            skipped_no_chassis += 1
            continue

        print(f"Importing {ui_name}...")
        mech_dict = import_mech(mechdef, chassis, args.armor_divisor)

        if mech_dict is None:
            skipped_no_walkmp += 1
            continue

        if not mech_dict["weapons"]:
            print(f"  WARNING: No mappable weapons for {ui_name} — skipping")
            skipped_no_weapons += 1
            continue

        if not args.dry_run:
            filename = make_filename(ui_name)
            filepath = output_dir / filename
            if filepath.exists() and not args.overwrite:
                print(f"  -> {filepath.name} already exists, skipping (use --overwrite to replace)")
                skipped_existing += 1
                continue
            with open(filepath, "w") as f:
                json.dump(mech_dict, f, indent=2)
                f.write("\n")
            print(f"  -> {filepath.name}")

        imported += 1

    print(f"\nDone: {imported} imported, "
          f"{skipped_blacklisted} blacklisted, "
          f"{skipped_existing} existing, "
          f"{skipped_no_chassis} missing chassis, "
          f"{skipped_no_walkmp} missing walk_mp, "
          f"{skipped_no_weapons} no weapons")


if __name__ == "__main__":
    main()
