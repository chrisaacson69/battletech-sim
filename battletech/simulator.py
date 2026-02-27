"""Combat loop and Monte Carlo runner."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .mech import Mech
from .combat import resolve_all_attacks, get_range_modifier
from .heat import apply_heat_phase, get_heat_mp_penalty


@dataclass
class FightResult:
    winner: str | None       # "A", "B", or None for draw
    winner_name: str | None  # mech name of winner
    rounds: int
    mech_a_remaining_hp: int
    mech_b_remaining_hp: int
    mech_a_damage_dealt: int
    mech_b_damage_dealt: int
    log: list[str] = field(default_factory=list)


@dataclass
class MonteCarloResult:
    mech_a_name: str
    mech_b_name: str
    fights: int
    mech_a_wins: int
    mech_b_wins: int
    draws: int
    mech_a_avg_remaining_hp: float
    mech_b_avg_remaining_hp: float
    avg_rounds: float
    mech_a_max_hp: int
    mech_b_max_hp: int

    @property
    def mech_a_win_pct(self) -> float:
        return self.mech_a_wins / self.fights * 100 if self.fights else 0

    @property
    def mech_b_win_pct(self) -> float:
        return self.mech_b_wins / self.fights * 100 if self.fights else 0

    @property
    def draw_pct(self) -> float:
        return self.draws / self.fights * 100 if self.fights else 0

    @property
    def empirical_bv_ratio(self) -> float:
        """Ratio of empirical combat effectiveness (A / B).

        Based on win rate: if A wins 75% and B wins 25%, ratio is 3.0.
        Uses +0.5 smoothing to avoid division by zero.
        """
        a_score = self.mech_a_wins + 0.5
        b_score = self.mech_b_wins + 0.5
        return a_score / b_score


def select_weapons_to_fire(mech: Mech, distance: int,
                           heat_factor: float = 1.0) -> list:
    """Weapon selection AI: sort by damage/heat efficiency, fire within heat budget.

    Strategy: collect all in-range weapons, sort by damage-per-heat (descending),
    then greedily fire while projected end-of-round heat stays manageable.
    Tolerance of +5 allows modest heat buildup per round (~3 rounds to danger).
    Always fires at least one weapon if anything is in range.
    """
    from .heat import calculate_heat_dissipation

    available = []
    for mw in mech.weapons:
        if mw.destroyed:
            continue
        if mw.ammo_remaining is not None and mw.ammo_remaining <= 0:
            continue
        range_mod = get_range_modifier(mw, distance)
        if range_mod is None:
            continue
        available.append(mw)

    if not available:
        return []

    # Sort by damage/heat efficiency (descending)
    # Cluster weapons: total damage = per-missile × cluster_size
    # Guard against heat=0 (Machine Gun) with max(..., 0.5)
    def weapon_efficiency(mw):
        total_dmg = mw.weapon.damage * (mw.weapon.cluster_size or 1)
        return total_dmg / max(mw.weapon.heat, 0.5)

    available.sort(key=weapon_efficiency, reverse=True)

    dissipation = calculate_heat_dissipation(mech, heat_factor)

    # Account for movement heat already committed this round
    movement_heat = 0
    if mech.movement_mode == "walk":
        movement_heat = 1
    elif mech.movement_mode == "run":
        movement_heat = 2
    elif mech.movement_mode == "jump":
        movement_heat = max(mech.jump_mp, 3)

    # Greedy fill: fire weapons while projected end-of-round heat <= 1
    # projected = current_heat + movement_heat + weapon_heat_total - dissipation
    selected = []
    cumulative_weapon_heat = 0

    for mw in available:
        projected = (mech.current_heat + movement_heat
                     + cumulative_weapon_heat + mw.weapon.heat
                     - dissipation)
        if projected <= 5 or not selected:
            selected.append(mw)
            cumulative_weapon_heat += mw.weapon.heat

    return selected


def choose_movement(mech: Mech) -> tuple[str, int]:
    """Simple movement AI: walk for moderate defense.

    Returns (mode, hexes_moved).
    """
    mp_penalty = get_heat_mp_penalty(mech.current_heat)
    effective_walk = max(0, mech.walk_mp - mp_penalty)

    if effective_walk <= 0:
        return "stand", 0
    return "walk", effective_walk


def heat_neutral_dpr(mech: Mech, distance: int,
                     heat_factor: float = 1.0) -> float:
    """Compute heat-neutral damage per round at a given distance.

    Fractional weapon firing: if total weapon heat exceeds dissipation,
    scale damage proportionally.  This gives a clean DPR curve without
    heat management complexity.
    """
    from .heat import calculate_heat_dissipation

    total_dmg = 0
    total_heat = 0
    for mw in mech.weapons:
        if mw.destroyed:
            continue
        if mw.ammo_remaining is not None and mw.ammo_remaining <= 0:
            continue
        rm = get_range_modifier(mw, distance)
        if rm is None:
            continue
        total_dmg += mw.weapon.damage * (mw.weapon.cluster_size or 1)
        total_heat += mw.weapon.heat

    if total_heat <= 0:
        return float(total_dmg)

    dissipation = calculate_heat_dissipation(mech, heat_factor)
    return total_dmg * min(1.0, dissipation / total_heat)


def find_preferred_range(mech: Mech, opponent: Mech,
                         max_range: int = 30,
                         heat_factor: float = 1.0) -> int:
    """Find range where mech has best DPR advantage over opponent.

    If outgunned at all ranges, picks the range with the smallest deficit.
    """
    best_range = 1
    best_advantage = -999.0

    for r in range(1, max_range + 1):
        advantage = heat_neutral_dpr(mech, r, heat_factor) - heat_neutral_dpr(opponent, r, heat_factor)
        if advantage > best_advantage:
            best_advantage = advantage
            best_range = r

    return best_range


def optimal_movement(mech_a: Mech, mech_b: Mech,
                     current_distance: int,
                     heat_factor: float = 1.0) -> tuple:
    """Compute movement for optimal range management.

    Simple reactive rule based on who is winning the current exchange:
    - Winning (higher DPR at current range): walk backward (kite)
    - Losing (lower DPR): run forward (close to change dynamic)
    - Equal: both walk toward each other (mutual approach)

    Forward always beats backward (run > walk), so range always closes.
    The winner just slows the closure by kiting.

    Returns (a_mode, a_hexes, b_mode, b_hexes, new_distance).
    """
    dpr_a = heat_neutral_dpr(mech_a, current_distance, heat_factor)
    dpr_b = heat_neutral_dpr(mech_b, current_distance, heat_factor)

    mp_pen_a = get_heat_mp_penalty(mech_a.current_heat)
    mp_pen_b = get_heat_mp_penalty(mech_b.current_heat)
    walk_a = max(0, mech_a.walk_mp - mp_pen_a)
    run_a = max(0, mech_a.run_mp - mp_pen_a)
    walk_b = max(0, mech_b.walk_mp - mp_pen_b)
    run_b = max(0, mech_b.run_mp - mp_pen_b)

    if dpr_a > dpr_b:
        # A winning — kites backward; B losing — charges forward
        a_mode, a_hexes = "walk", walk_a
        b_mode, b_hexes = "run", run_b
        net_closure = run_b - walk_a
    elif dpr_b > dpr_a:
        # B winning — kites backward; A losing — charges forward
        b_mode, b_hexes = "walk", walk_b
        a_mode, a_hexes = "run", run_a
        net_closure = run_a - walk_b
    else:
        # Equal — mutual approach
        a_mode, a_hexes = "walk", walk_a
        b_mode, b_hexes = "walk", walk_b
        net_closure = walk_a + walk_b

    new_distance = max(1, current_distance - net_closure)
    return a_mode, a_hexes, b_mode, b_hexes, new_distance


def fight(mech_a: Mech, mech_b: Mech, distance: int = 6,
          max_rounds: int = 50, debug: bool = False,
          closing_rate: int = 0,
          movement_ai: str = "closure",
          heat_factor: float = 1.0) -> FightResult:
    """Run a single fight between two mechs.

    Args:
        mech_a, mech_b: The combatants (will be mutated).
        distance: Starting distance in hexes.
        max_rounds: Safety cap on rounds.
        debug: If True, collect detailed log.
        closing_rate: Hexes to close per round (used by static/closure modes).
        movement_ai: "static" (fixed range), "closure" (close per round),
                     or "optimal" (each mech picks run/walk based on DPR).
    """
    log: list[str] = []
    mech_a_damage = 0
    mech_b_damage = 0
    a_hp_start = mech_a.max_total_hp
    b_hp_start = mech_b.max_total_hp

    current_distance = distance

    last_round = 0
    for round_num in range(1, max_rounds + 1):
        if not mech_a.active or not mech_b.active:
            break
        last_round = round_num

        if debug:
            log.append(f"\n=== Round {round_num} (distance: {current_distance}) ===")

        # --- Movement Phase ---
        if movement_ai == "optimal":
            a_mode, a_hexes, b_mode, b_hexes, new_dist = optimal_movement(
                mech_a, mech_b, current_distance, heat_factor)
        else:
            a_mode, a_hexes = choose_movement(mech_a)
            b_mode, b_hexes = choose_movement(mech_b)
            new_dist = None  # handled below

        mech_a.movement_mode = a_mode
        mech_a.hexes_moved = a_hexes
        mech_b.movement_mode = b_mode
        mech_b.hexes_moved = b_hexes

        if movement_ai == "optimal":
            if debug:
                pref_a = find_preferred_range(mech_a, mech_b, heat_factor=heat_factor)
                pref_b = find_preferred_range(mech_b, mech_a, heat_factor=heat_factor)
                log.append(f"  {mech_a.name}: {a_mode} ({a_hexes} hexes) wants range {pref_a}")
                log.append(f"  {mech_b.name}: {b_mode} ({b_hexes} hexes) wants range {pref_b}")
                log.append(f"  Distance: {current_distance} -> {new_dist}")
            current_distance = new_dist
        elif debug:
            log.append(f"  {mech_a.name}: {a_mode} ({a_hexes} hexes)")
            log.append(f"  {mech_b.name}: {b_mode} ({b_hexes} hexes)")

        # --- Weapon Selection Phase ---
        a_weapons = select_weapons_to_fire(mech_a, current_distance, heat_factor)
        b_weapons = select_weapons_to_fire(mech_b, current_distance, heat_factor)

        if debug:
            log.append(f"  {mech_a.name} fires: {[w.weapon.name for w in a_weapons]}")
            log.append(f"  {mech_b.name} fires: {[w.weapon.name for w in b_weapons]}")

        # --- Attack Phase (simultaneous) ---
        # Both mechs fire, resolve damage
        # We snapshot the weapon lists before resolution since it's simultaneous
        a_results = resolve_all_attacks(mech_a, mech_b, current_distance,
                                         weapons_to_fire=a_weapons, debug=debug)
        b_results = resolve_all_attacks(mech_b, mech_a, current_distance,
                                         weapons_to_fire=b_weapons, debug=debug)

        for r in a_results:
            mech_a_damage += r.damage_dealt
            if debug and r.events:
                log.extend(r.events)

        for r in b_results:
            mech_b_damage += r.damage_dealt
            if debug and r.events:
                log.extend(r.events)

        # --- Heat Phase ---
        if mech_a.active:
            a_heat_events = apply_heat_phase(mech_a, a_weapons, debug, heat_factor)
            if debug:
                log.extend(a_heat_events)

        if mech_b.active:
            b_heat_events = apply_heat_phase(mech_b, b_weapons, debug, heat_factor)
            if debug:
                log.extend(b_heat_events)

        # --- End of Round ---
        if debug:
            log.append(
                f"  Status: {mech_a.name} HP={mech_a.total_hp}/{a_hp_start} heat={mech_a.current_heat}"
                f"  |  {mech_b.name} HP={mech_b.total_hp}/{b_hp_start} heat={mech_b.current_heat}"
            )

        # Close distance (static/closure modes — optimal handled in movement phase)
        if movement_ai != "optimal" and closing_rate > 0:
            current_distance = max(1, current_distance - closing_rate)

    # Determine winner by side (A/B), not by name (handles mirror matches)
    a_alive = mech_a.active
    b_alive = mech_b.active

    if a_alive and not b_alive:
        winner_side = "A"
        winner_name = mech_a.name
    elif b_alive and not a_alive:
        winner_side = "B"
        winner_name = mech_b.name
    elif not a_alive and not b_alive:
        winner_side = None
        winner_name = None
    else:
        # Both alive after max rounds — winner by remaining HP percentage
        a_pct = mech_a.total_hp / a_hp_start if a_hp_start else 0
        b_pct = mech_b.total_hp / b_hp_start if b_hp_start else 0
        if a_pct > b_pct:
            winner_side = "A"
            winner_name = mech_a.name
        elif b_pct > a_pct:
            winner_side = "B"
            winner_name = mech_b.name
        else:
            winner_side = None
            winner_name = None

    return FightResult(
        winner=winner_side,
        winner_name=winner_name,
        rounds=last_round,
        mech_a_remaining_hp=mech_a.total_hp,
        mech_b_remaining_hp=mech_b.total_hp,
        mech_a_damage_dealt=mech_a_damage,
        mech_b_damage_dealt=mech_b_damage,
        log=log,
    )


def monte_carlo(mech_a_template: Mech, mech_b_template: Mech,
                n: int = 10000, distance: int = 6,
                max_rounds: int = 50,
                closing_rate: int = 0,
                movement_ai: str = "closure",
                heat_factor: float = 1.0) -> MonteCarloResult:
    """Run n fights and collect statistics."""
    a_wins = 0
    b_wins = 0
    draws = 0
    a_hp_total = 0
    b_hp_total = 0
    rounds_total = 0

    for _ in range(n):
        a = mech_a_template.copy()
        b = mech_b_template.copy()
        result = fight(a, b, distance=distance, max_rounds=max_rounds,
                       closing_rate=closing_rate, movement_ai=movement_ai,
                       heat_factor=heat_factor)

        if result.winner == "A":
            a_wins += 1
        elif result.winner == "B":
            b_wins += 1
        else:
            draws += 1

        a_hp_total += result.mech_a_remaining_hp
        b_hp_total += result.mech_b_remaining_hp
        rounds_total += result.rounds

    return MonteCarloResult(
        mech_a_name=mech_a_template.name,
        mech_b_name=mech_b_template.name,
        fights=n,
        mech_a_wins=a_wins,
        mech_b_wins=b_wins,
        draws=draws,
        mech_a_avg_remaining_hp=a_hp_total / n,
        mech_b_avg_remaining_hp=b_hp_total / n,
        avg_rounds=rounds_total / n,
        mech_a_max_hp=mech_a_template.max_total_hp,
        mech_b_max_hp=mech_b_template.max_total_hp,
    )
