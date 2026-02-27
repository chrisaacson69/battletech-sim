"""Damage soak test: empirical mech durability measurement.

Throws standardized damage at a mech using the existing damage pipeline
(hit locations, crits, ammo explosions, transfers) until dead. Measures
total damage absorbed across thousands of iterations per mech.

Two damage profiles based on Level 1 weapon quanta:
- Concentrated: random 5-15 damage per hit (direct-fire weapons)
- Cluster: 2 damage per hit, individual location rolls (missile scatter)
- Mixed: randomly alternates between concentrated and cluster each hit
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum

from .mech import Mech
from .tables import roll_hit_location


class DamageProfile(Enum):
    CONCENTRATED = "concentrated"
    CLUSTER = "cluster"
    MIXED = "mixed"


# Concentrated: random damage in this range per hit
CONCENTRATED_MIN = 5
CONCENTRATED_MAX = 15

# Cluster: fixed small hits
CLUSTER_DAMAGE = 2

# Safety cap — 11x the heaviest mech's HP
MAX_DAMAGE = 5000


@dataclass
class DeathCause:
    """Breakdown of how a mech died across iterations."""
    ct_cored: int = 0
    head_destroyed: int = 0
    ammo_explosion: int = 0
    xl_side_torso: int = 0

    @property
    def total(self) -> int:
        return self.ct_cored + self.head_destroyed + self.ammo_explosion + self.xl_side_torso

    def pct(self, cause: str) -> float:
        t = self.total
        if t == 0:
            return 0.0
        return getattr(self, cause) / t * 100


@dataclass
class SoakProfileResult:
    """Result for a single damage profile across N iterations."""
    profile: DamageProfile
    iterations: int
    dtk_values: list[int] = field(default_factory=list)
    death_causes: DeathCause = field(default_factory=DeathCause)
    capped_count: int = 0
    log: list[str] = field(default_factory=list)

    @property
    def avg_dtk(self) -> float:
        return sum(self.dtk_values) / len(self.dtk_values) if self.dtk_values else 0

    @property
    def min_dtk(self) -> int:
        return min(self.dtk_values) if self.dtk_values else 0

    @property
    def max_dtk(self) -> int:
        return max(self.dtk_values) if self.dtk_values else 0

    @property
    def std_dtk(self) -> float:
        if len(self.dtk_values) < 2:
            return 0.0
        avg = self.avg_dtk
        variance = sum((x - avg) ** 2 for x in self.dtk_values) / (len(self.dtk_values) - 1)
        return math.sqrt(variance)


@dataclass
class SoakResult:
    """Complete soak test result for one mech across all profiles."""
    mech_name: str
    tonnage: int
    weight_class: str
    max_hp: int
    total_armor: int
    total_structure: int
    engine_type: str
    auto_case: bool = False
    profiles: dict[DamageProfile, SoakProfileResult] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)

    def efficiency(self, profile: DamageProfile) -> float:
        """DTK / max HP."""
        pr = self.profiles.get(profile)
        if not pr or self.max_hp == 0:
            return 0.0
        return pr.avg_dtk / self.max_hp


def _classify_death(mech: Mech, last_events: list[str]) -> str:
    """Determine primary cause of death from mech state and killing hit's events.

    Checks ammo explosion first because it can *cause* CT/head destruction.
    Uses only the last hit's events to avoid false attribution from earlier
    non-lethal explosions.
    """
    for event in last_events:
        if "AMMO EXPLOSION" in event:
            return "ammo_explosion"

    if mech.locations["HD"].destroyed:
        return "head_destroyed"

    if mech.engine_type == "xl":
        if mech.locations["LT"].destroyed or mech.locations["RT"].destroyed:
            return "xl_side_torso"

    return "ct_cored"


def _prep_mech(mech: Mech, auto_case: bool = False) -> None:
    """Prepare a mech copy for soak testing.

    - Halves all ammo (represents mid-fight state — mech has been shooting)
    - Optionally applies CASE to all locations (HBS rules)
    """
    for mw in mech.weapons:
        if mw.ammo_remaining is not None:
            mw.ammo_remaining = mw.ammo_remaining // 2

    if auto_case:
        for loc in mech.locations.values():
            loc.has_case = True


def _apply_concentrated(mech: Mech) -> tuple[int, list[str]]:
    """Apply one concentrated hit: random 5-15 damage to a single location."""
    dmg = random.randint(CONCENTRATED_MIN, CONCENTRATED_MAX)
    loc = roll_hit_location("front")
    events = mech.apply_damage(loc, dmg)
    return dmg, events


def _apply_cluster(mech: Mech) -> tuple[int, list[str]]:
    """Apply one cluster hit: 2 damage to a random location."""
    loc = roll_hit_location("front")
    events = mech.apply_damage(loc, CLUSTER_DAMAGE)
    return CLUSTER_DAMAGE, events


def soak_single(mech_template: Mech, profile: DamageProfile,
                iterations: int = 10000, debug: bool = False,
                auto_case: bool = False) -> SoakProfileResult:
    """Run the soak test for one mech with one damage profile."""
    result = SoakProfileResult(profile=profile, iterations=iterations)
    all_log: list[str] = []

    for _ in range(iterations):
        mech = mech_template.copy()
        _prep_mech(mech, auto_case=auto_case)
        total_damage = 0
        hit_num = 0
        last_events: list[str] = []

        while not mech.is_dead and total_damage < MAX_DAMAGE:
            hit_num += 1

            if profile == DamageProfile.MIXED:
                if random.random() < 0.5:
                    dmg, events = _apply_concentrated(mech)
                else:
                    dmg, events = _apply_cluster(mech)
            elif profile == DamageProfile.CONCENTRATED:
                dmg, events = _apply_concentrated(mech)
            else:
                dmg, events = _apply_cluster(mech)

            total_damage += dmg
            last_events = events

            if debug:
                all_log.append(f"  Hit {hit_num}: {dmg} dmg ({profile.value})")
                all_log.extend(events)

        if not mech.is_dead:
            result.capped_count += 1

        result.dtk_values.append(total_damage)

        if mech.is_dead:
            cause = _classify_death(mech, last_events)
            setattr(result.death_causes, cause,
                    getattr(result.death_causes, cause) + 1)

    if debug:
        result.log = all_log

    return result


def run_soak_test(mech_template: Mech, iterations: int = 10000,
                  profiles: list[DamageProfile] | None = None,
                  debug: bool = False, auto_case: bool = False) -> SoakResult:
    """Run the complete soak test for one mech across all profiles."""
    if profiles is None:
        profiles = [DamageProfile.CONCENTRATED, DamageProfile.CLUSTER, DamageProfile.MIXED]

    if debug:
        iterations = 1

    result = SoakResult(
        mech_name=mech_template.name,
        tonnage=mech_template.tonnage,
        weight_class=mech_template.metadata.weight_class or "unknown",
        max_hp=mech_template.max_total_hp,
        total_armor=mech_template.total_armor,
        total_structure=mech_template.total_structure,
        engine_type=mech_template.engine_type,
        auto_case=auto_case,
    )

    for profile in profiles:
        profile_result = soak_single(mech_template, profile, iterations, debug,
                                     auto_case=auto_case)
        result.profiles[profile] = profile_result
        if debug and profile_result.log:
            result.log.append(f"\n{'='*50}")
            result.log.append(f"  {profile.value.upper()} PROFILE")
            result.log.append(f"{'='*50}")
            result.log.extend(profile_result.log)

    return result


def run_soak_tournament(mechs: dict[str, Mech], iterations: int = 10000,
                        weight_filter: str | None = None,
                        auto_case: bool = False) -> list[SoakResult]:
    """Run soak tests on all mechs. Returns sorted by mixed DTK descending."""
    filtered = mechs
    if weight_filter:
        filtered = {
            name: mech for name, mech in mechs.items()
            if mech.metadata.weight_class == weight_filter
        }

    results: list[SoakResult] = []
    names = sorted(filtered.keys())
    for i, name in enumerate(names, 1):
        print(f"  [{i}/{len(names)}] {name}...", flush=True)
        mech = filtered[name]
        sr = run_soak_test(mech, iterations, auto_case=auto_case)
        results.append(sr)

    results.sort(
        key=lambda r: r.profiles.get(
            DamageProfile.MIXED,
            SoakProfileResult(DamageProfile.MIXED, 0)
        ).avg_dtk,
        reverse=True,
    )

    return results


def format_soak_result(result: SoakResult) -> str:
    """Format a single mech's soak test result for terminal output."""
    lines: list[str] = []

    rules = "HBS (auto-CASE)" if result.auto_case else "Tabletop"
    lines.append(f"Soak Test: {result.mech_name} ({result.tonnage}t, {result.weight_class})")
    lines.append(f"Max HP: {result.max_hp} (armor: {result.total_armor}, structure: {result.total_structure})")
    lines.append(f"Engine: {result.engine_type}  |  Rules: {rules}  |  Ammo: half")

    first_profile = next(iter(result.profiles.values()), None)
    if first_profile:
        lines.append(f"Iterations: {first_profile.iterations}")

    lines.append("")
    lines.append(f"{'Profile':<16s} {'Avg DTK':>8s} {'Min':>6s} {'Max':>6s} {'StdDev':>7s} {'Eff':>6s}")
    lines.append("-" * 52)

    for profile in [DamageProfile.CONCENTRATED, DamageProfile.CLUSTER, DamageProfile.MIXED]:
        pr = result.profiles.get(profile)
        if not pr:
            continue
        eff = result.efficiency(profile)
        lines.append(
            f"{profile.value.capitalize():<16s} "
            f"{pr.avg_dtk:>8.0f} "
            f"{pr.min_dtk:>6d} "
            f"{pr.max_dtk:>6d} "
            f"{pr.std_dtk:>7.0f} "
            f"{eff:>5.2f}x"
        )
        if pr.capped_count > 0:
            lines.append(f"  WARNING: {pr.capped_count} iterations hit damage cap ({MAX_DAMAGE})")

    mixed = result.profiles.get(DamageProfile.MIXED)
    if mixed and mixed.death_causes.total > 0:
        lines.append("")
        lines.append(f"Death Causes ({DamageProfile.MIXED.value}):")
        dc = mixed.death_causes
        if dc.ct_cored > 0:
            lines.append(f"  CT cored:        {dc.pct('ct_cored'):>5.1f}%")
        if dc.head_destroyed > 0:
            lines.append(f"  Head destroyed:  {dc.pct('head_destroyed'):>5.1f}%")
        if dc.ammo_explosion > 0:
            lines.append(f"  Ammo explosion:  {dc.pct('ammo_explosion'):>5.1f}%")
        if dc.xl_side_torso > 0:
            lines.append(f"  XL side torso:   {dc.pct('xl_side_torso'):>5.1f}%")

    return "\n".join(lines)


def format_soak_tournament(results: list[SoakResult]) -> str:
    """Format tournament table for terminal output."""
    lines: list[str] = []

    header = (
        f"{'Name':<30s} {'Tons':>4s} {'HP':>5s} "
        f"{'Conc':>6s} {'Clust':>6s} {'Mixed':>6s} "
        f"{'Eff':>5s} {'Ammo%':>6s}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for r in results:
        conc = r.profiles.get(DamageProfile.CONCENTRATED)
        clust = r.profiles.get(DamageProfile.CLUSTER)
        mixed = r.profiles.get(DamageProfile.MIXED)

        conc_dtk = conc.avg_dtk if conc else 0
        clust_dtk = clust.avg_dtk if clust else 0
        mixed_dtk = mixed.avg_dtk if mixed else 0
        eff = r.efficiency(DamageProfile.MIXED)
        ammo_pct = mixed.death_causes.pct('ammo_explosion') if mixed else 0.0

        lines.append(
            f"{r.mech_name:<30s} {r.tonnage:>4d} {r.max_hp:>5d} "
            f"{conc_dtk:>6.0f} {clust_dtk:>6.0f} {mixed_dtk:>6.0f} "
            f"{eff:>4.2f}x {ammo_pct:>5.1f}%"
        )

    lines.append(f"\n{len(results)} mechs tested")
    return "\n".join(lines)
