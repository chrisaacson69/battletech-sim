"""CLI entry point for BattleTech combat simulator."""

import argparse
import sys
import time
from pathlib import Path

from battletech.mech import load_mechs_from_file, load_mechs_from_directory
from battletech.simulator import fight, monte_carlo
from battletech.soak import run_soak_test, run_soak_tournament, format_soak_result, format_soak_tournament


def load_mechs(data_path: Path) -> dict:
    """Load mechs from a file or directory, auto-detecting which."""
    if data_path.is_dir():
        return load_mechs_from_directory(data_path)
    elif data_path.is_file():
        return load_mechs_from_file(data_path)
    else:
        print(f"Error: Mech data path not found: {data_path}")
        sys.exit(1)


def print_mech_list(mechs: dict, weight_filter: str | None = None):
    """Print available mechs in a formatted table."""
    rows = []
    for name, mech in sorted(mechs.items(), key=lambda x: (x[1].tonnage, x[0])):
        wc = mech.metadata.weight_class or "unknown"
        if weight_filter and wc != weight_filter:
            continue
        source = mech.metadata.source or "manual"
        rows.append((name, mech.tonnage, wc, source))

    if not rows:
        print("No mechs found matching filter.")
        return

    print(f"\n{'Name':35s} {'Tons':>4s}  {'Class':10s} {'Source':8s}")
    print("-" * 62)
    for name, tons, wc, source in rows:
        print(f"{name:35s} {tons:>4d}  {wc:10s} {source:8s}")
    print(f"\n{len(rows)} mechs total")


def main():
    parser = argparse.ArgumentParser(description="BattleTech Monte Carlo Combat Simulator")
    parser.add_argument("--mech-a", help="Name of first mech")
    parser.add_argument("--mech-b", help="Name of second mech")
    parser.add_argument("--fights", type=int, default=10000, help="Number of fights to simulate")
    parser.add_argument("--distance", type=int, default=6, help="Starting distance in hexes")
    parser.add_argument("--closing-rate", type=int, default=None,
                        help="Hexes to close per round (0 = fixed distance)")
    parser.add_argument("--movement", type=str, choices=["static", "closure", "optimal"],
                        default="closure",
                        help="Movement mode: static (fixed range) or closure (close 1/round)")
    parser.add_argument("--max-rounds", type=int, default=50, help="Max rounds per fight")
    parser.add_argument("--debug", action="store_true", help="Run one fight with detailed log")
    parser.add_argument("--data", type=str, default="data/mechs",
                        help="Path to mech definitions (file or directory)")
    parser.add_argument("--list", action="store_true", help="List available mechs and exit")
    parser.add_argument("--filter-weight", type=str, choices=["light", "medium", "heavy", "assault"],
                        help="Filter mechs by weight class (used with --list or --soak-all)")
    parser.add_argument("--soak", type=str, metavar="MECH_NAME",
                        help="Run damage soak test on a single mech")
    parser.add_argument("--soak-all", action="store_true",
                        help="Run damage soak test on all mechs (tournament)")
    parser.add_argument("--iterations", type=int, default=10000,
                        help="Iterations per profile for soak test (default: 10000)")
    parser.add_argument("--case", action="store_true",
                        help="Auto-CASE on all locations (HBS rules, soak test only)")
    args = parser.parse_args()

    # Resolve movement mode and closing rate
    movement_ai = args.movement
    if args.closing_rate is not None:
        closing_rate = args.closing_rate
    elif movement_ai == "static":
        closing_rate = 0
    else:
        closing_rate = 1

    # Load mechs
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = Path(__file__).parent / data_path

    mechs = load_mechs(data_path)

    # List mode
    if args.list:
        print_mech_list(mechs, args.filter_weight)
        return

    # Soak test mode (single mech)
    if args.soak:
        if args.soak not in mechs:
            print(f"Error: Mech '{args.soak}' not found. Use --list to see available mechs.")
            sys.exit(1)
        mech = mechs[args.soak]
        print(f"\nRunning soak test: {mech.name}")
        if not args.debug:
            print(f"Iterations: {args.iterations}")
        print()
        start = time.time()
        result = run_soak_test(mech, iterations=args.iterations, debug=args.debug,
                              auto_case=args.case)
        elapsed = time.time() - start
        if args.debug:
            for line in result.log:
                print(line)
            print()
        print(format_soak_result(result))
        print(f"\nCompleted in {elapsed:.1f}s")
        return

    # Soak tournament mode (all mechs)
    if args.soak_all:
        print(f"\nSoak Tournament ({args.iterations} iterations per mech per profile)")
        if args.filter_weight:
            print(f"Weight filter: {args.filter_weight}")
        print()
        start = time.time()
        results = run_soak_tournament(mechs, iterations=args.iterations,
                                      weight_filter=args.filter_weight,
                                      auto_case=args.case)
        elapsed = time.time() - start
        print()
        print(format_soak_tournament(results))
        print(f"\nCompleted in {elapsed:.1f}s")
        return

    # Combat mode — require mech names
    if not args.mech_a or not args.mech_b:
        print("Error: --mech-a and --mech-b are required for combat simulation.")
        print("Use --list to see available mechs.")
        sys.exit(1)

    if args.mech_a not in mechs:
        print(f"Error: Mech '{args.mech_a}' not found. Available: {list(mechs.keys())}")
        sys.exit(1)
    if args.mech_b not in mechs:
        print(f"Error: Mech '{args.mech_b}' not found. Available: {list(mechs.keys())}")
        sys.exit(1)

    mech_a = mechs[args.mech_a]
    mech_b = mechs[args.mech_b]

    if args.debug:
        # Single fight with logging
        a = mech_a.copy()
        b = mech_b.copy()
        result = fight(a, b, distance=args.distance, max_rounds=args.max_rounds,
                       debug=True, closing_rate=closing_rate,
                       movement_ai=movement_ai)
        print(f"\n{'='*60}")
        print(f"  {mech_a.name} vs {mech_b.name}")
        print(f"  Starting distance: {args.distance} hexes")
        print(f"{'='*60}")
        for line in result.log:
            print(line)
        print(f"\n{'='*60}")
        print(f"  Winner: {result.winner_name or 'DRAW'}")
        print(f"  Rounds: {result.rounds}")
        print(f"  {mech_a.name}: {result.mech_a_remaining_hp} HP remaining, dealt {result.mech_a_damage_dealt} damage")
        print(f"  {mech_b.name}: {result.mech_b_remaining_hp} HP remaining, dealt {result.mech_b_damage_dealt} damage")
        print(f"{'='*60}")
    else:
        # Monte Carlo
        print(f"\nSimulating {args.fights} fights: {mech_a.name} vs {mech_b.name}")
        if movement_ai == "optimal":
            mode_label = "optimal (DPR-based)"
        elif closing_rate == 0:
            mode_label = "static"
        else:
            mode_label = f"closing {closing_rate}/round"
        print(f"Distance: {args.distance} hexes, {mode_label}")
        print(f"Max rounds: {args.max_rounds}")
        print()

        start = time.time()
        result = monte_carlo(mech_a, mech_b, n=args.fights,
                             distance=args.distance, max_rounds=args.max_rounds,
                             closing_rate=closing_rate,
                             movement_ai=movement_ai)
        elapsed = time.time() - start

        print(f"{'='*60}")
        print(f"  Results ({args.fights} fights, {elapsed:.1f}s)")
        print(f"{'='*60}")
        print(f"  {result.mech_a_name:30s}  {result.mech_a_wins:>6d} wins ({result.mech_a_win_pct:.1f}%)")
        print(f"  {result.mech_b_name:30s}  {result.mech_b_wins:>6d} wins ({result.mech_b_win_pct:.1f}%)")
        print(f"  {'Draws':30s}  {result.draws:>6d}      ({result.draw_pct:.1f}%)")
        print(f"{'='*60}")
        print(f"  Avg rounds:       {result.avg_rounds:.1f}")
        print(f"  {result.mech_a_name} avg HP remaining: {result.mech_a_avg_remaining_hp:.0f}/{result.mech_a_max_hp}")
        print(f"  {result.mech_b_name} avg HP remaining: {result.mech_b_avg_remaining_hp:.0f}/{result.mech_b_max_hp}")
        print(f"  Empirical BV ratio (A/B):     {result.empirical_bv_ratio:.2f}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
