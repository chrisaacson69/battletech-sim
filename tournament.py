"""Round-robin assault mech tournament across ranges and gunnery levels."""

import argparse
import sys
import time
from pathlib import Path

from battletech.mech import load_mechs_from_directory
from battletech.simulator import monte_carlo


RANGES = [3, 6, 12]
GUNNERY_LEVELS = [4, 3]
FIGHTS_PER_MATCHUP = 1000
MAX_ROUNDS = 50
WEIGHT_CLASS = "assault"


def run_tournament(mechs: dict, gunnery: int, distance: int,
                   fights: int = FIGHTS_PER_MATCHUP,
                   closing_rate: int = 1,
                   movement_ai: str = "closure") -> dict:
    """Run round-robin and return {mech_name: {wins, losses, draws, avg_rounds, damage_dealt, damage_taken}}."""
    names = sorted(mechs.keys())
    stats = {
        name: {"wins": 0, "losses": 0, "draws": 0, "rounds_total": 0,
               "fights": 0, "dmg_dealt": 0, "dmg_taken": 0}
        for name in names
    }

    total_matchups = len(names) * (len(names) - 1) // 2
    matchup_num = 0

    for i, name_a in enumerate(names):
        for name_b in names[i + 1:]:
            matchup_num += 1
            mech_a = mechs[name_a].copy()
            mech_b = mechs[name_b].copy()
            mech_a.gunnery = gunnery
            mech_b.gunnery = gunnery

            result = monte_carlo(mech_a, mech_b, n=fights,
                                 distance=distance, max_rounds=MAX_ROUNDS,
                                 closing_rate=closing_rate,
                                 movement_ai=movement_ai)

            stats[name_a]["wins"] += result.mech_a_wins
            stats[name_a]["losses"] += result.mech_b_wins
            stats[name_a]["draws"] += result.draws
            stats[name_a]["fights"] += fights
            stats[name_a]["rounds_total"] += result.avg_rounds * fights

            stats[name_b]["wins"] += result.mech_b_wins
            stats[name_b]["losses"] += result.mech_a_wins
            stats[name_b]["draws"] += result.draws
            stats[name_b]["fights"] += fights
            stats[name_b]["rounds_total"] += result.avg_rounds * fights

            # Track damage via remaining HP
            a_dmg_dealt = (mech_b.max_total_hp * fights) - (result.mech_b_avg_remaining_hp * fights)
            b_dmg_dealt = (mech_a.max_total_hp * fights) - (result.mech_a_avg_remaining_hp * fights)
            stats[name_a]["dmg_dealt"] += a_dmg_dealt
            stats[name_a]["dmg_taken"] += b_dmg_dealt
            stats[name_b]["dmg_dealt"] += b_dmg_dealt
            stats[name_b]["dmg_taken"] += a_dmg_dealt

            sys.stdout.write(f"\r  [{matchup_num}/{total_matchups}] {name_a} vs {name_b}          ")
            sys.stdout.flush()

    print()
    return stats


def format_standings(stats: dict, gunnery: int, distance: int,
                     closing_rate: int = 1, fights: int = FIGHTS_PER_MATCHUP,
                     movement_ai: str = "closure") -> str:
    """Format tournament standings table."""
    lines = []
    lines.append(f"\n{'='*80}")
    if movement_ai == "optimal":
        mode_label = "Optimal"
    elif movement_ai == "static" or closing_rate == 0:
        mode_label = "Static"
    else:
        mode_label = f"Closing: {closing_rate}/round"
    lines.append(f"  ASSAULT TOURNAMENT — Distance: {distance} hexes, Gunnery: {gunnery}, "
                 f"{mode_label}")
    lines.append(f"  {fights} fights per matchup, {len(stats)} mechs, "
                 f"{len(stats) * (len(stats)-1) // 2} matchups")
    lines.append(f"{'='*80}")

    # Sort by win rate descending
    ranked = sorted(stats.items(), key=lambda x: x[1]["wins"] / max(x[1]["fights"], 1), reverse=True)

    lines.append(f"{'#':>2s} {'Name':<28s} {'W':>5s} {'L':>5s} {'D':>4s} "
                 f"{'Win%':>6s} {'AvgRd':>5s} {'DmgD':>7s} {'DmgT':>7s} {'D/T':>5s}")
    lines.append("-" * 80)

    for rank, (name, s) in enumerate(ranked, 1):
        total = s["fights"]
        win_pct = s["wins"] / total * 100 if total else 0
        avg_rounds = s["rounds_total"] / total if total else 0
        dmg_dealt = s["dmg_dealt"] / total if total else 0
        dmg_taken = s["dmg_taken"] / total if total else 0
        dt_ratio = dmg_dealt / dmg_taken if dmg_taken > 0 else 999

        lines.append(f"{rank:>2d} {name:<28s} {s['wins']:>5d} {s['losses']:>5d} {s['draws']:>4d} "
                     f"{win_pct:>5.1f}% {avg_rounds:>5.1f} {dmg_dealt:>7.1f} {dmg_taken:>7.1f} {dt_ratio:>5.2f}")

    return "\n".join(lines)


def format_comparison(all_results: dict) -> str:
    """Format A/B gunnery comparison summary."""
    lines = []
    lines.append(f"\n{'='*80}")
    lines.append(f"  A/B COMPARISON: Gunnery 4 vs Gunnery 3")
    lines.append(f"{'='*80}")

    for dist in RANGES:
        g4 = all_results.get((4, dist), {})
        g3 = all_results.get((3, dist), {})
        if not g4 or not g3:
            continue

        lines.append(f"\n  Distance {dist} hexes:")
        lines.append(f"  {'Name':<28s} {'G4 Win%':>8s} {'G3 Win%':>8s} {'Delta':>7s} {'G4 AvgRd':>8s} {'G3 AvgRd':>8s}")
        lines.append(f"  {'-'*70}")

        # Sort by G4 win rate
        ranked = sorted(g4.items(), key=lambda x: x[1]["wins"] / max(x[1]["fights"], 1), reverse=True)

        for name, s4 in ranked:
            s3 = g3.get(name, {"wins": 0, "fights": 1, "rounds_total": 0})
            wp4 = s4["wins"] / s4["fights"] * 100
            wp3 = s3["wins"] / s3["fights"] * 100
            ar4 = s4["rounds_total"] / s4["fights"]
            ar3 = s3["rounds_total"] / s3["fights"]
            delta = wp3 - wp4
            sign = "+" if delta >= 0 else ""
            lines.append(f"  {name:<28s} {wp4:>7.1f}% {wp3:>7.1f}% {sign}{delta:>5.1f}% {ar4:>8.1f} {ar3:>8.1f}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Round-robin assault mech tournament")
    parser.add_argument("--movement", type=str,
                        choices=["static", "closure", "optimal"],
                        default="closure",
                        help="Movement mode: static, closure, or optimal (DPR-based)")
    parser.add_argument("--fights", type=int, default=FIGHTS_PER_MATCHUP,
                        help=f"Fights per matchup (default: {FIGHTS_PER_MATCHUP})")
    parser.add_argument("--filter-weight", type=str,
                        choices=["light", "medium", "heavy", "assault"],
                        default="assault", help="Weight class filter (default: assault)")
    args = parser.parse_args()

    movement_ai = args.movement
    closing_rate = 0 if movement_ai == "static" else 1

    data_path = Path(__file__).parent / "data" / "mechs"
    all_mechs = load_mechs_from_directory(data_path)

    # Filter by weight class
    mechs = {
        name: mech for name, mech in all_mechs.items()
        if mech.metadata.weight_class == args.filter_weight
    }
    print(f"\nLoaded {len(mechs)} {args.filter_weight} mechs")
    if movement_ai == "optimal":
        mode_label = "optimal (DPR-based)"
    elif closing_rate == 0:
        mode_label = "static"
    else:
        mode_label = f"closure ({closing_rate}/round)"
    print(f"Movement: {mode_label}, {args.fights} fights per matchup")

    all_results = {}
    total_start = time.time()

    for gunnery in GUNNERY_LEVELS:
        for distance in RANGES:
            print(f"\nRunning: Gunnery {gunnery}, Distance {distance} hexes...")
            start = time.time()
            stats = run_tournament(mechs, gunnery, distance,
                                   fights=args.fights,
                                   closing_rate=closing_rate,
                                   movement_ai=movement_ai)
            elapsed = time.time() - start

            all_results[(gunnery, distance)] = stats
            print(format_standings(stats, gunnery, distance,
                                   closing_rate=closing_rate,
                                   fights=args.fights,
                                   movement_ai=movement_ai))
            print(f"\n  Completed in {elapsed:.1f}s")

    # A/B Comparison
    print(format_comparison(all_results))

    total_elapsed = time.time() - total_start
    print(f"\n{'='*80}")
    print(f"  Total time: {total_elapsed:.1f}s")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
