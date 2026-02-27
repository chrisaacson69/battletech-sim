"""Combat resolution: to-hit calculation, damage application, crit resolution."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .mech import Mech, MountedWeapon
from .tables import roll_2d6, roll_hit_location, roll_cluster_hits


@dataclass
class AttackResult:
    weapon_name: str
    target_number: int
    roll: int
    hit: bool
    location_hit: str | None = None
    damage_dealt: int = 0
    events: list[str] | None = None


def get_range_modifier(weapon: MountedWeapon, distance: int) -> int | None:
    """Return range modifier, or None if out of range / inside minimum range."""
    w = weapon.weapon
    if distance < w.min_range:
        # Inside minimum range: +1 for each hex inside min range
        return w.min_range - distance
    if distance <= w.short_range:
        return 0
    if distance <= w.medium_range:
        return 2
    if distance <= w.long_range:
        return 4
    return None  # Out of range


def get_attacker_movement_modifier(movement_mode: str) -> int:
    if movement_mode == "stand":
        return 0
    if movement_mode == "walk":
        return 1
    if movement_mode == "run":
        return 2
    if movement_mode == "jump":
        return 3
    return 0


def get_heat_to_hit_modifier(current_heat: int) -> int:
    if current_heat >= 24:
        return 4
    if current_heat >= 17:
        return 3
    if current_heat >= 13:
        return 2
    if current_heat >= 8:
        return 1
    return 0


def calculate_target_number(
    attacker: Mech,
    weapon: MountedWeapon,
    target: Mech,
    distance: int,
    terrain_modifier: int = 0,
) -> int | None:
    """Calculate the to-hit target number. Returns None if shot is impossible."""
    range_mod = get_range_modifier(weapon, distance)
    if range_mod is None:
        return None  # Out of range

    from .tables import get_target_movement_modifier

    tn = attacker.gunnery
    tn += get_attacker_movement_modifier(attacker.movement_mode)
    tn += get_target_movement_modifier(target.hexes_moved)
    tn += range_mod
    tn += get_heat_to_hit_modifier(attacker.current_heat)
    tn += terrain_modifier

    # Pulse lasers get -2 to hit
    if "Pulse" in weapon.weapon.name:
        tn -= 2

    return tn


def resolve_attack(
    attacker: Mech,
    weapon: MountedWeapon,
    target: Mech,
    distance: int,
    direction: str = "front",
    terrain_modifier: int = 0,
    debug: bool = False,
) -> AttackResult:
    """Resolve a single weapon attack against a target."""
    if weapon.destroyed:
        return AttackResult(weapon.weapon.name, 99, 0, False)

    if weapon.ammo_remaining is not None and weapon.ammo_remaining <= 0:
        return AttackResult(weapon.weapon.name, 99, 0, False, events=["Out of ammo"])

    tn = calculate_target_number(attacker, weapon, target, distance, terrain_modifier)
    if tn is None:
        return AttackResult(weapon.weapon.name, 99, 0, False, events=["Out of range"])

    # Streak SRMs: check hit first, if miss, no ammo consumed, no heat
    is_streak = weapon.weapon.is_streak

    roll = roll_2d6()
    hit = roll >= tn and roll != 2  # 2 always misses

    if not hit:
        if not is_streak and weapon.ammo_remaining is not None:
            weapon.ammo_remaining -= 1
        return AttackResult(weapon.weapon.name, tn, roll, False)

    # Consume ammo
    if weapon.ammo_remaining is not None:
        weapon.ammo_remaining -= 1

    events: list[str] = []
    total_damage = 0

    w = weapon.weapon
    if w.cluster_size > 0:
        # Cluster weapon: roll how many hit, then each missile rolls location
        if is_streak:
            # Streak: all missiles hit
            missiles_hit = w.cluster_size
        else:
            missiles_hit = roll_cluster_hits(w.cluster_size)

        events.append(f"{w.name}: {missiles_hit}/{w.cluster_size} missiles hit")

        for _ in range(missiles_hit):
            loc = roll_hit_location(direction)
            dmg = w.damage_per_missile
            total_damage += dmg
            if debug:
                events.append(f"  Missile -> {loc} for {dmg}")
            hit_events = target.apply_damage(loc, dmg, debug=debug)
            events.extend(hit_events)
            if not target.active:
                break
    else:
        # Single-hit weapon
        loc = roll_hit_location(direction)
        dmg = w.damage
        total_damage = dmg
        events.append(f"{w.name}: hit {loc} for {dmg} damage")
        hit_events = target.apply_damage(loc, dmg, debug=debug)
        events.extend(hit_events)

    # Ultra AC: fire second shot
    if w.is_ultra and weapon.ammo_remaining and weapon.ammo_remaining > 0:
        jam_roll = roll_2d6()
        if jam_roll == 2:
            events.append(f"{w.name} JAMMED on ultra shot!")
            weapon.destroyed = True  # jammed for rest of fight
        else:
            # Second shot
            roll2 = roll_2d6()
            hit2 = roll2 >= tn and roll2 != 2
            weapon.ammo_remaining -= 1
            if hit2:
                loc2 = roll_hit_location(direction)
                total_damage += w.damage
                events.append(f"{w.name} ultra: hit {loc2} for {w.damage}")
                events.extend(target.apply_damage(loc2, w.damage, debug=debug))

    return AttackResult(
        weapon_name=w.name,
        target_number=tn,
        roll=roll,
        hit=True,
        damage_dealt=total_damage,
        events=events,
    )


def resolve_all_attacks(
    attacker: Mech,
    target: Mech,
    distance: int,
    direction: str = "front",
    weapons_to_fire: list[MountedWeapon] | None = None,
    terrain_modifier: int = 0,
    debug: bool = False,
) -> list[AttackResult]:
    """Resolve all weapon attacks from attacker against target.

    Attacks are resolved simultaneously — target damage is applied as we go
    but the attacker's weapon list was decided before resolution.
    """
    if weapons_to_fire is None:
        weapons_to_fire = [
            mw for mw in attacker.weapons
            if not mw.destroyed
            and (mw.ammo_remaining is None or mw.ammo_remaining > 0)
            and get_range_modifier(mw, distance) is not None
        ]

    results: list[AttackResult] = []
    for mw in weapons_to_fire:
        if not target.active:
            break
        result = resolve_attack(attacker, mw, target, distance, direction,
                                terrain_modifier, debug)
        results.append(result)

    return results
