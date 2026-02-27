"""Mech data model with damage application logic."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

from typing import Optional

from .weapons import Weapon, WEAPON_DB
from .tables import (
    INTERNAL_STRUCTURE, TRANSFER_MAP, REAR_ARMOR_LOCATIONS,
    roll_hit_location, roll_critical_hits,
)


@dataclass
class MechMetadata:
    source: str = "manual"
    bv2: Optional[int] = None
    cost_cbills: Optional[int] = None
    tech_base: Optional[str] = None
    year_introduced: Optional[int] = None
    era: Optional[str] = None
    role: Optional[str] = None
    weight_class: Optional[str] = None


@dataclass
class Location:
    name: str
    max_armor: int
    current_armor: int
    rear_max_armor: int       # 0 for non-torso locations
    rear_current_armor: int
    max_structure: int
    current_structure: int
    destroyed: bool = False
    crittable_slots: list[str] = field(default_factory=list)
    has_case: bool = False

    @property
    def transfer_to(self) -> str | None:
        return TRANSFER_MAP.get(self.name)

    @property
    def total_hp(self) -> int:
        return self.current_armor + self.rear_current_armor + self.current_structure


@dataclass
class MountedWeapon:
    weapon: Weapon
    location: str
    ammo_remaining: int | None = None  # None for energy weapons
    destroyed: bool = False

    def __post_init__(self):
        if self.ammo_remaining is None and self.weapon.ammo_per_ton is not None:
            self.ammo_remaining = self.weapon.ammo_per_ton


@dataclass
class Mech:
    name: str
    tonnage: int
    walk_mp: int
    run_mp: int
    jump_mp: int
    gunnery: int
    piloting: int
    locations: dict[str, Location]
    weapons: list[MountedWeapon]
    heat_sinks: int
    double_heat_sinks: bool
    engine_type: str          # "standard", "xl", "light"
    metadata: MechMetadata = field(default_factory=MechMetadata)
    current_heat: int = 0
    active: bool = True

    # Combat state
    movement_mode: str = "stand"   # "stand", "walk", "run", "jump"
    hexes_moved: int = 0

    @property
    def is_dead(self) -> bool:
        """Mech is dead if CT or HD structure is gone, or XL engine lost a side torso."""
        if not self.active:
            return True
        ct = self.locations.get("CT")
        hd = self.locations.get("HD")
        if ct and ct.destroyed:
            return True
        if hd and hd.destroyed:
            return True
        if self.engine_type == "xl":
            lt = self.locations.get("LT")
            rt = self.locations.get("RT")
            if (lt and lt.destroyed) or (rt and rt.destroyed):
                return True
        return False

    @property
    def total_armor(self) -> int:
        return sum(
            loc.current_armor + loc.rear_current_armor
            for loc in self.locations.values()
        )

    @property
    def total_structure(self) -> int:
        return sum(loc.current_structure for loc in self.locations.values())

    @property
    def total_hp(self) -> int:
        return self.total_armor + self.total_structure

    @property
    def max_total_hp(self) -> int:
        return sum(
            loc.max_armor + loc.rear_max_armor + loc.max_structure
            for loc in self.locations.values()
        )

    def apply_damage(self, location_id: str, damage: int, is_rear: bool = False,
                     debug: bool = False) -> list[str]:
        """Apply damage to a location, handling armor→structure→transfer→destruction.

        Returns a list of event strings for debug logging.
        """
        events: list[str] = []
        loc = self.locations[location_id]

        if loc.destroyed:
            # Transfer to next location
            transfer = loc.transfer_to
            if transfer:
                events.append(f"  {location_id} already destroyed, transferring {damage} to {transfer}")
                return events + self.apply_damage(transfer, damage, is_rear=False, debug=debug)
            else:
                events.append(f"  {location_id} destroyed, no transfer target — damage lost")
                return events

        # Apply to rear armor if applicable
        if is_rear and location_id in REAR_ARMOR_LOCATIONS:
            if loc.rear_current_armor > 0:
                absorbed = min(loc.rear_current_armor, damage)
                loc.rear_current_armor -= absorbed
                damage -= absorbed
                events.append(f"  {location_id} rear armor: -{absorbed} (remaining: {loc.rear_current_armor})")
        else:
            # Apply to front armor
            if loc.current_armor > 0:
                absorbed = min(loc.current_armor, damage)
                loc.current_armor -= absorbed
                damage -= absorbed
                events.append(f"  {location_id} armor: -{absorbed} (remaining: {loc.current_armor})")

        if damage <= 0:
            return events

        # Armor breached — damage goes to structure
        structure_absorbed = min(loc.current_structure, damage)
        loc.current_structure -= structure_absorbed
        damage -= structure_absorbed
        events.append(f"  {location_id} structure: -{structure_absorbed} (remaining: {loc.current_structure})")

        # Roll for crits when structure takes damage
        if structure_absorbed > 0 and loc.current_structure > 0:
            num_crits = roll_critical_hits()
            if num_crits > 0:
                events.extend(self._apply_crits(location_id, num_crits, debug))

        # Check for location destruction
        if loc.current_structure <= 0:
            loc.destroyed = True
            events.append(f"  {location_id} DESTROYED!")

            # Destroy weapons in this location
            for mw in self.weapons:
                if mw.location == location_id:
                    mw.destroyed = True

            # Check for mech death
            if self.is_dead:
                self.active = False
                events.append(f"  {self.name} KILLED!")
                return events

            # Transfer remaining damage
            if damage > 0:
                transfer = loc.transfer_to
                if transfer:
                    events.append(f"  Transferring {damage} damage to {transfer}")
                    events.extend(self.apply_damage(transfer, damage, is_rear=False, debug=debug))

        return events

    def _apply_crits(self, location_id: str, num_crits: int,
                     debug: bool = False) -> list[str]:
        """Apply critical hits to a location's crittable slots."""
        import random
        events: list[str] = []
        loc = self.locations[location_id]

        available_slots = [s for s in loc.crittable_slots if s != "DESTROYED"]
        if not available_slots:
            return events

        for _ in range(num_crits):
            available_slots = [s for s in loc.crittable_slots if s != "DESTROYED"]
            if not available_slots:
                break

            slot_idx = random.randint(0, len(loc.crittable_slots) - 1)
            while loc.crittable_slots[slot_idx] == "DESTROYED":
                slot_idx = random.randint(0, len(loc.crittable_slots) - 1)

            hit_item = loc.crittable_slots[slot_idx]
            loc.crittable_slots[slot_idx] = "DESTROYED"
            events.append(f"  CRIT: {hit_item} in {location_id}!")

            # Check if it's a weapon — destroy weapon and all its slots
            for mw in self.weapons:
                if mw.location == location_id and mw.weapon.name == hit_item and not mw.destroyed:
                    mw.destroyed = True
                    # Multi-slot weapons: destroy all remaining slots of this weapon
                    if mw.weapon.crit_slots > 1:
                        for i, s in enumerate(loc.crittable_slots):
                            if s == hit_item:
                                loc.crittable_slots[i] = "DESTROYED"
                    break

            # Check for ammo explosion
            if hit_item.startswith("Ammo"):
                events.extend(self._ammo_explosion(location_id, hit_item, debug))

            # Check for engine hit
            if hit_item == "Engine":
                # Count engine crits
                engine_crits = sum(
                    1 for loc2 in self.locations.values()
                    for s in loc2.crittable_slots
                    if s == "DESTROYED" and "Engine" in (loc2.crittable_slots + [""])
                )
                # Actually, track engine hits differently
                # For simplicity: 3 engine crits = destruction
                pass

        return events

    def _ammo_explosion(self, location_id: str, ammo_slot: str,
                        debug: bool = False) -> list[str]:
        """Handle ammo explosion in a location."""
        events: list[str] = []
        loc = self.locations[location_id]

        # Find the ammo and its remaining damage
        # For simplicity: each ammo ton does its weapon's damage × remaining shots
        # In practice, we'll cap at a reasonable explosion damage
        # Standard rule: ammo explodes for (rounds_remaining × damage_per_round)

        # Find the mounted weapon that uses this ammo
        ammo_damage = 0
        for mw in self.weapons:
            if mw.location == location_id and mw.ammo_remaining and mw.ammo_remaining > 0:
                if ammo_slot == f"Ammo {mw.weapon.name}":
                    if mw.weapon.cluster_size > 0:
                        ammo_damage = mw.ammo_remaining * mw.weapon.damage_per_missile * mw.weapon.cluster_size
                    else:
                        ammo_damage = mw.ammo_remaining * mw.weapon.damage
                    mw.ammo_remaining = 0
                    break

        if ammo_damage <= 0:
            # Default: 20 damage for unknown ammo
            ammo_damage = 20

        if loc.has_case:
            events.append(f"  CASE contains ammo explosion in {location_id} ({ammo_damage} damage)")
            loc.current_structure = 0
            loc.current_armor = 0
            loc.rear_current_armor = 0
            loc.destroyed = True
            for mw in self.weapons:
                if mw.location == location_id:
                    mw.destroyed = True
        else:
            events.append(f"  AMMO EXPLOSION in {location_id}! ({ammo_damage} damage to internals)")
            # Apply explosion damage directly to structure
            events.extend(self.apply_damage(location_id, ammo_damage, debug=debug))

        return events

    def copy(self) -> Mech:
        """Deep copy for running fresh fights."""
        return copy.deepcopy(self)


def load_mech(data: dict) -> Mech:
    """Load a Mech from a JSON-compatible dictionary."""
    tonnage = data["tonnage"]
    structure_table = INTERNAL_STRUCTURE[tonnage]

    locations: dict[str, Location] = {}
    for loc_data in data["locations"]:
        loc_id = loc_data["name"]
        struct = structure_table[loc_id]
        # Expand crittable_slots: weapons occupy multiple TT crit slots
        raw_slots = list(loc_data.get("crittable_slots", []))
        expanded_slots: list[str] = []
        for slot_name in raw_slots:
            if slot_name in WEAPON_DB:
                expanded_slots.extend([slot_name] * WEAPON_DB[slot_name].crit_slots)
            else:
                expanded_slots.append(slot_name)
        locations[loc_id] = Location(
            name=loc_id,
            max_armor=loc_data["armor"],
            current_armor=loc_data["armor"],
            rear_max_armor=loc_data.get("rear_armor", 0),
            rear_current_armor=loc_data.get("rear_armor", 0),
            max_structure=struct,
            current_structure=struct,
            crittable_slots=expanded_slots,
            has_case=loc_data.get("has_case", False),
        )

    weapons: list[MountedWeapon] = []
    for w_data in data["weapons"]:
        weapon = WEAPON_DB[w_data["name"]]
        ammo = w_data.get("ammo", None)
        weapons.append(MountedWeapon(
            weapon=weapon,
            location=w_data["location"],
            ammo_remaining=ammo,
        ))

    # Parse optional metadata block
    meta_raw = data.get("metadata", {})
    metadata = MechMetadata(
        source=meta_raw.get("source", "manual"),
        bv2=meta_raw.get("bv2"),
        cost_cbills=meta_raw.get("cost_cbills"),
        tech_base=meta_raw.get("tech_base"),
        year_introduced=meta_raw.get("year_introduced"),
        era=meta_raw.get("era"),
        role=meta_raw.get("role"),
        weight_class=meta_raw.get("weight_class"),
    )

    return Mech(
        name=data["name"],
        tonnage=tonnage,
        walk_mp=data["walk_mp"],
        run_mp=data.get("run_mp", int(data["walk_mp"] * 1.5 + 0.5)),
        jump_mp=data.get("jump_mp", 0),
        gunnery=data.get("gunnery", 4),
        piloting=data.get("piloting", 5),
        locations=locations,
        weapons=weapons,
        heat_sinks=data["heat_sinks"],
        double_heat_sinks=data.get("double_heat_sinks", False),
        engine_type=data.get("engine_type", "standard"),
        metadata=metadata,
    )


def load_mechs_from_file(filepath: str | Path) -> dict[str, Mech]:
    """Load all mechs from a JSON file. Returns dict keyed by mech name."""
    with open(filepath) as f:
        data = json.load(f)
    return {m["name"]: load_mech(m) for m in data["mechs"]}


def load_mechs_from_directory(dirpath: str | Path) -> dict[str, Mech]:
    """Load all mechs from individual JSON files in a directory.

    Each file should contain a single mech definition (bare dict, no wrapper).
    Returns dict keyed by mech name.
    """
    dirpath = Path(dirpath)
    mechs: dict[str, Mech] = {}
    for filepath in sorted(dirpath.glob("*.json")):
        with open(filepath) as f:
            data = json.load(f)
        mech = load_mech(data)
        mechs[mech.name] = mech
    return mechs
