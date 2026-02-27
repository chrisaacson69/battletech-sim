"""Heat tracking and effects for BattleTech combat."""

from __future__ import annotations

import random

from .mech import Mech, MountedWeapon
from .tables import roll_2d6


def calculate_heat_generated(mech: Mech, weapons_fired: list[MountedWeapon]) -> int:
    """Calculate total heat generated from movement + weapons fired."""
    heat = 0

    # Movement heat
    if mech.movement_mode == "walk":
        heat += 1
    elif mech.movement_mode == "run":
        heat += 2
    elif mech.movement_mode == "jump":
        heat += max(mech.jump_mp, 3)  # minimum 3 heat for jumping

    # Weapon heat
    for mw in weapons_fired:
        if not mw.destroyed:
            heat += mw.weapon.heat
            # Ultra AC fires twice
            if mw.weapon.is_ultra:
                heat += mw.weapon.heat

    return heat


def calculate_heat_dissipation(mech: Mech) -> int:
    """Calculate heat dissipated by heat sinks."""
    per_sink = 2 if mech.double_heat_sinks else 1
    return mech.heat_sinks * per_sink


def apply_heat_phase(mech: Mech, weapons_fired: list[MountedWeapon],
                     debug: bool = False) -> list[str]:
    """Run the heat phase: generate, dissipate, check effects.

    Returns list of event strings.
    """
    events: list[str] = []

    generated = calculate_heat_generated(mech, weapons_fired)
    dissipated = calculate_heat_dissipation(mech)

    mech.current_heat += generated
    mech.current_heat -= dissipated
    mech.current_heat = max(0, mech.current_heat)

    if debug or mech.current_heat >= 5:
        events.append(
            f"  Heat: +{generated} generated, -{dissipated} dissipated "
            f"= {mech.current_heat} current"
        )

    # Check heat effects
    if mech.current_heat >= 30:
        events.append(f"  {mech.name} AUTOMATIC SHUTDOWN (heat {mech.current_heat})")
        mech.active = False
        return events

    if mech.current_heat >= 25:
        roll = roll_2d6()
        if roll >= 4:
            events.append(f"  {mech.name} SHUTDOWN (heat {mech.current_heat}, rolled {roll})")
            mech.active = False
            return events

    elif mech.current_heat >= 19:
        roll = roll_2d6()
        if roll >= 6:
            events.append(f"  {mech.name} SHUTDOWN (heat {mech.current_heat}, rolled {roll})")
            mech.active = False
            return events

    elif mech.current_heat >= 14:
        roll = roll_2d6()
        if roll >= 8:
            events.append(f"  {mech.name} SHUTDOWN (heat {mech.current_heat}, rolled {roll})")
            mech.active = False
            return events

    # Ammo explosion check at 18+ heat
    if mech.current_heat >= 18:
        has_ammo = any(
            mw.ammo_remaining and mw.ammo_remaining > 0
            for mw in mech.weapons
        )
        if has_ammo:
            roll = roll_2d6()
            if roll >= 4:
                events.append(
                    f"  {mech.name} AMMO EXPLOSION from heat! "
                    f"(heat {mech.current_heat}, rolled {roll})"
                )
                # Find a random ammo-carrying weapon and explode it
                ammo_weapons = [
                    mw for mw in mech.weapons
                    if mw.ammo_remaining and mw.ammo_remaining > 0
                ]
                if ammo_weapons:
                    victim = random.choice(ammo_weapons)
                    events.extend(
                        mech._ammo_explosion(victim.location, f"Ammo {victim.weapon.name}", debug)
                    )

    return events


def get_heat_mp_penalty(current_heat: int) -> int:
    """Return MP penalty from heat."""
    if current_heat >= 9:
        return 4  # -5 MP at 10+, but we cap at reasonable
    if current_heat >= 5:
        # 5+: -1 MP, 9+: -2 MP (we'll keep it simple with the table)
        pass

    penalty = 0
    if current_heat >= 5:
        penalty += 1
    if current_heat >= 10:
        penalty += 1
    if current_heat >= 15:
        penalty += 1
    if current_heat >= 20:
        penalty += 1
    if current_heat >= 25:
        penalty += 1
    return penalty
