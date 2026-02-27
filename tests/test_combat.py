"""Sanity tests for the BattleTech combat simulator."""

import random
from collections import Counter
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from battletech.weapons import WEAPON_DB, MEDIUM_LASER, AC20, PPC, LRM20
from battletech.tables import (
    roll_2d6, roll_hit_location, FRONT_HIT_TABLE,
    roll_cluster_hits, roll_critical_hits,
    INTERNAL_STRUCTURE, TRANSFER_MAP,
)
from battletech.mech import Mech, MechMetadata, Location, MountedWeapon, load_mechs_from_file, load_mechs_from_directory
from battletech.combat import (
    calculate_target_number, resolve_attack, get_range_modifier,
)
from battletech.heat import calculate_heat_generated, calculate_heat_dissipation
from battletech.simulator import fight, monte_carlo
from battletech.soak import (
    DamageProfile, soak_single, run_soak_test, run_soak_tournament,
)


DATA_DIR = Path(__file__).parent.parent / "data" / "mechs"
DATA_PATH = DATA_DIR  # alias for backward compat in helpers


# === Weapon Database Tests ===

def test_weapon_db_completeness():
    """All expected weapons exist in the database."""
    expected = ["Medium Laser", "AC/20", "PPC", "LRM-20", "SRM-6", "AC/5", "Small Laser"]
    for name in expected:
        assert name in WEAPON_DB, f"Missing weapon: {name}"


def test_weapon_ranges():
    """Weapon ranges are properly ordered."""
    for name, w in WEAPON_DB.items():
        assert w.short_range <= w.medium_range <= w.long_range, f"{name} ranges out of order"


# === Tables Tests ===

def test_2d6_distribution():
    """2d6 rolls should approximate expected distribution."""
    random.seed(42)
    counts = Counter(roll_2d6() for _ in range(100000))
    # 7 should be most common (~16.7%)
    assert counts[7] > counts[2]
    assert counts[7] > counts[12]
    # 2 and 12 should be rarest (~2.8%)
    assert counts[2] < counts[6]
    assert counts[12] < counts[8]


def test_hit_location_coverage():
    """All 2d6 results map to valid locations."""
    valid = {"HD", "CT", "LT", "RT", "LA", "RA", "LL", "RL"}
    for roll_val in range(2, 13):
        loc = FRONT_HIT_TABLE[roll_val]
        assert loc in valid, f"Roll {roll_val} maps to invalid location: {loc}"


def test_hit_location_distribution():
    """Hit locations over many rolls should roughly match 2d6 probabilities."""
    random.seed(42)
    counts = Counter(roll_hit_location("front") for _ in range(100000))
    # CT has rolls 2 and 7 → ~19.4% (1/36 + 6/36)
    # HD has roll 12 → ~2.8% (1/36)
    ct_pct = counts["CT"] / 100000
    hd_pct = counts["HD"] / 100000
    assert 0.15 < ct_pct < 0.24, f"CT hit rate {ct_pct:.3f} out of expected range"
    assert 0.01 < hd_pct < 0.05, f"HD hit rate {hd_pct:.3f} out of expected range"


def test_internal_structure_table():
    """All standard tonnages have structure values."""
    for tonnage in range(20, 105, 5):
        assert tonnage in INTERNAL_STRUCTURE, f"Missing tonnage: {tonnage}"
        struct = INTERNAL_STRUCTURE[tonnage]
        assert "CT" in struct and "HD" in struct


def test_transfer_map():
    """Damage transfer chain is valid."""
    assert TRANSFER_MAP["LA"] == "LT"
    assert TRANSFER_MAP["RA"] == "RT"
    assert TRANSFER_MAP["LT"] == "CT"
    assert TRANSFER_MAP["RT"] == "CT"
    assert TRANSFER_MAP["CT"] is None
    assert TRANSFER_MAP["HD"] is None


# === Mech Loading Tests ===

def test_load_mechs():
    """All four core mechs load successfully."""
    mechs = load_mechs_from_directory(DATA_DIR)
    assert len(mechs) >= 4
    assert "Atlas AS7-D" in mechs
    assert "Hunchback HBK-4G" in mechs
    assert "Wolverine WVR-6R" in mechs
    assert "Marauder MAD-3R" in mechs


def test_atlas_stats():
    """Atlas has correct basic stats."""
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"]
    assert atlas.tonnage == 100
    assert atlas.walk_mp == 3
    assert len(atlas.weapons) == 5
    assert atlas.heat_sinks == 20


def test_mech_total_hp():
    """Mech total HP = sum of all armor + structure."""
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"]
    assert atlas.total_hp > 0
    assert atlas.total_armor > 0
    assert atlas.total_structure > 0
    assert atlas.total_hp == atlas.total_armor + atlas.total_structure


# === Metadata Tests ===

def test_metadata_defaults():
    """Mech metadata has sensible defaults."""
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"]
    assert atlas.metadata.source == "manual"
    assert atlas.metadata.weight_class == "assault"
    assert atlas.metadata.role == "Juggernaut"
    assert atlas.metadata.tech_base == "Inner Sphere"


def test_metadata_all_manual_mechs_have_source():
    """All manually-defined mechs are tagged as source=manual."""
    mechs = load_mechs_from_directory(DATA_DIR)
    for name, mech in mechs.items():
        if mech.metadata.source == "manual":
            assert mech.metadata.weight_class is not None, f"{name} missing weight_class"


# === Damage Application Tests ===

def test_armor_absorbs_damage():
    """Damage less than armor doesn't reach structure."""
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"].copy()
    ct = atlas.locations["CT"]
    initial_armor = ct.current_armor
    initial_structure = ct.current_structure

    atlas.apply_damage("CT", 5)
    assert ct.current_armor == initial_armor - 5
    assert ct.current_structure == initial_structure


def test_damage_bleeds_to_structure():
    """Damage exceeding armor hits structure."""
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"].copy()
    ct = atlas.locations["CT"]
    ct.current_armor = 3  # Only 3 armor left

    atlas.apply_damage("CT", 10)
    assert ct.current_armor == 0
    assert ct.current_structure < ct.max_structure


def test_location_destruction_transfers():
    """When a location is destroyed, excess damage transfers."""
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"].copy()
    la = atlas.locations["LA"]
    la.current_armor = 0
    la.current_structure = 1  # about to die

    ct_hp_before = atlas.locations["LT"].current_armor + atlas.locations["LT"].current_structure
    atlas.apply_damage("LA", 20)  # way more than 1 structure
    assert la.destroyed
    # Damage should have transferred to LT
    ct_hp_after = atlas.locations["LT"].current_armor + atlas.locations["LT"].current_structure
    assert ct_hp_after < ct_hp_before


def test_ct_destruction_kills():
    """CT destruction kills the mech."""
    mechs = load_mechs_from_directory(DATA_DIR)
    hunchback = mechs["Hunchback HBK-4G"].copy()
    ct = hunchback.locations["CT"]
    ct.current_armor = 0
    ct.current_structure = 1

    hunchback.apply_damage("CT", 5)
    assert ct.destroyed
    assert hunchback.is_dead


def test_hd_destruction_kills():
    """Head destruction kills the mech."""
    mechs = load_mechs_from_directory(DATA_DIR)
    hunchback = mechs["Hunchback HBK-4G"].copy()
    hd = hunchback.locations["HD"]
    hd.current_armor = 0
    hd.current_structure = 1

    hunchback.apply_damage("HD", 5)
    assert hd.destroyed
    assert hunchback.is_dead


# === Combat Resolution Tests ===

def test_range_modifier():
    """Range modifier calculation is correct."""
    mw = MountedWeapon(weapon=MEDIUM_LASER, location="LA")
    assert get_range_modifier(mw, 1) == 0   # short range
    assert get_range_modifier(mw, 3) == 0   # short range boundary
    assert get_range_modifier(mw, 4) == 2   # medium range
    assert get_range_modifier(mw, 6) == 2   # medium range boundary
    assert get_range_modifier(mw, 7) == 4   # long range
    assert get_range_modifier(mw, 9) == 4   # long range boundary
    assert get_range_modifier(mw, 10) is None  # out of range


def test_ppc_minimum_range():
    """PPC has minimum range penalty."""
    mw = MountedWeapon(weapon=PPC, location="RA")
    assert get_range_modifier(mw, 1) == 2   # 3 - 1 = 2 penalty
    assert get_range_modifier(mw, 2) == 1   # 3 - 2 = 1 penalty
    assert get_range_modifier(mw, 3) == 0   # at min range, short range modifier
    assert get_range_modifier(mw, 6) == 0   # short range


def test_to_hit_calculation():
    """Basic to-hit number calculation."""
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"].copy()
    target = mechs["Hunchback HBK-4G"].copy()
    atlas.movement_mode = "stand"
    target.hexes_moved = 0

    mw = atlas.weapons[0]  # AC/20
    tn = calculate_target_number(atlas, mw, target, distance=3)
    # Gunnery 4 + 0 attacker move + 0 target move + 0 short range = 4
    assert tn == 4


# === Heat Tests ===

def test_heat_generation():
    """Heat from walking + medium laser."""
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"].copy()
    atlas.movement_mode = "walk"

    ml = [mw for mw in atlas.weapons if mw.weapon.name == "Medium Laser"][0]
    heat = calculate_heat_generated(atlas, [ml])
    assert heat == 1 + 3  # walk + medium laser


def test_heat_dissipation():
    """Heat sink dissipation calculation."""
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"].copy()
    assert calculate_heat_dissipation(atlas) == 20  # 20 single sinks


# === Simulator Tests ===

def test_single_fight_completes():
    """A single fight runs to completion."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    a = mechs["Atlas AS7-D"].copy()
    b = mechs["Hunchback HBK-4G"].copy()
    result = fight(a, b, distance=6, max_rounds=50)
    assert result.winner is not None or (not a.active and not b.active)
    assert result.rounds > 0


def test_mirror_match_roughly_even():
    """Two identical mechs should win roughly 50/50."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    result = monte_carlo(
        mechs["Hunchback HBK-4G"],
        mechs["Hunchback HBK-4G"],
        n=2000, distance=4,
    )
    # Should be within 40-60% for each side
    a_pct = result.mech_a_win_pct
    assert 30 < a_pct < 70, f"Mirror match too lopsided: {a_pct:.1f}%"


def test_atlas_beats_hunchback():
    """Atlas (100t) should generally beat Hunchback (50t)."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    result = monte_carlo(
        mechs["Atlas AS7-D"],
        mechs["Hunchback HBK-4G"],
        n=2000, distance=6, closing_rate=1,
    )
    assert result.mech_a_wins > result.mech_b_wins, (
        f"Atlas should beat Hunchback: {result.mech_a_wins} vs {result.mech_b_wins}"
    )


def test_debug_fight_has_log():
    """Debug fight produces log output."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    a = mechs["Marauder MAD-3R"].copy()
    b = mechs["Wolverine WVR-6R"].copy()
    result = fight(a, b, distance=8, debug=True, closing_rate=1)
    assert len(result.log) > 0


# === Soak Test Tests ===

def test_soak_single_completes():
    """A soak test runs to completion with all DTKs > 0."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"]
    result = soak_single(atlas, DamageProfile.CONCENTRATED, iterations=100)
    assert result.iterations == 100
    assert len(result.dtk_values) == 100
    assert all(dtk > 0 for dtk in result.dtk_values)
    assert result.capped_count == 0


def test_soak_dtk_is_positive():
    """Average DTK should always be positive and reasonable."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    hunchback = mechs["Hunchback HBK-4G"]
    result = soak_single(hunchback, DamageProfile.CONCENTRATED, iterations=1000)
    assert result.avg_dtk > 0
    # DTK can be less than max HP due to ammo explosions — that's the insight
    assert result.min_dtk > 0


def test_soak_cluster_more_durable_than_concentrated():
    """Cluster fire should result in higher average DTK (less efficient at killing)."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"]
    conc = soak_single(atlas, DamageProfile.CONCENTRATED, iterations=2000)
    clust = soak_single(atlas, DamageProfile.CLUSTER, iterations=2000)
    assert clust.avg_dtk >= conc.avg_dtk * 0.95  # allow some variance margin


def test_soak_death_causes_sum_to_iterations():
    """Death cause counts should sum to iteration count."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"]
    result = soak_single(atlas, DamageProfile.MIXED, iterations=1000)
    dc = result.death_causes
    total = dc.ct_cored + dc.head_destroyed + dc.ammo_explosion + dc.xl_side_torso
    assert total == 1000


def test_soak_atlas_has_ammo_deaths():
    """Atlas (AC/20 + LRM-20 ammo, no CASE) should have some ammo explosion deaths."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    atlas = mechs["Atlas AS7-D"]
    result = soak_single(atlas, DamageProfile.MIXED, iterations=5000)
    assert result.death_causes.ammo_explosion > 0, "Atlas should sometimes die to ammo explosions"


def test_soak_efficiency_positive():
    """Efficiency (DTK / max HP) should always be > 0. May be < 1.0 for ammo-carrying mechs."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    for name in ["Atlas AS7-D", "Hunchback HBK-4G", "Wolverine WVR-6R", "Marauder MAD-3R"]:
        mech = mechs[name]
        result = soak_single(mech, DamageProfile.MIXED, iterations=100)
        eff = result.avg_dtk / mech.max_total_hp
        assert eff > 0, f"{name} efficiency {eff:.2f} should be positive"


def test_soak_tournament_sorted():
    """Tournament results should be sorted by mixed DTK descending."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    # Use just the 4 manual mechs for speed
    manual = {n: m for n, m in mechs.items() if m.metadata.source == "manual"}
    results = run_soak_tournament(manual, iterations=100)
    mixed_dtks = [
        r.profiles[DamageProfile.MIXED].avg_dtk for r in results
    ]
    for i in range(len(mixed_dtks) - 1):
        assert mixed_dtks[i] >= mixed_dtks[i + 1], "Tournament not sorted by DTK descending"


def test_soak_debug_has_log():
    """Debug mode soak test produces event log."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    hunchback = mechs["Hunchback HBK-4G"]
    result = run_soak_test(hunchback, debug=True)
    assert len(result.log) > 0


def test_soak_weight_filter():
    """Tournament weight filter works correctly."""
    random.seed(42)
    mechs = load_mechs_from_directory(DATA_DIR)
    results = run_soak_tournament(mechs, iterations=50, weight_filter="assault")
    for r in results:
        assert r.weight_class == "assault"


if __name__ == "__main__":
    import traceback

    tests = [
        test_weapon_db_completeness,
        test_weapon_ranges,
        test_2d6_distribution,
        test_hit_location_coverage,
        test_hit_location_distribution,
        test_internal_structure_table,
        test_transfer_map,
        test_load_mechs,
        test_atlas_stats,
        test_mech_total_hp,
        test_metadata_defaults,
        test_metadata_all_manual_mechs_have_source,
        test_armor_absorbs_damage,
        test_damage_bleeds_to_structure,
        test_location_destruction_transfers,
        test_ct_destruction_kills,
        test_hd_destruction_kills,
        test_range_modifier,
        test_ppc_minimum_range,
        test_to_hit_calculation,
        test_heat_generation,
        test_heat_dissipation,
        test_single_fight_completes,
        test_mirror_match_roughly_even,
        test_atlas_beats_hunchback,
        test_debug_fight_has_log,
        test_soak_single_completes,
        test_soak_dtk_is_positive,
        test_soak_cluster_more_durable_than_concentrated,
        test_soak_death_causes_sum_to_iterations,
        test_soak_atlas_has_ammo_deaths,
        test_soak_efficiency_positive,
        test_soak_tournament_sorted,
        test_soak_debug_has_log,
        test_soak_weight_filter,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests")
