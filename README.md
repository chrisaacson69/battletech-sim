# BattleTech Combat Simulator

Monte Carlo combat simulator for BattleTech mechs. Runs thousands of fights to derive empirical Battle Value (BV) ratios between mechs.

## Usage

```bash
# Run 10,000 fights between two mechs
python main.py --mech-a "Atlas AS7-D" --mech-b "Marauder MAD-3R" --fights 10000

# Single debug fight with detailed log
python main.py --mech-a "Atlas AS7-D" --mech-b "Hunchback HBK-4G" --debug

# Custom distance and closing rate
python main.py --mech-a "Wolverine WVR-6R" --mech-b "Hunchback HBK-4G" --distance 12 --closing-rate 2
```

## Test Mechs

- **Hunchback HBK-4G** (50t) — AC/20 brawler
- **Wolverine WVR-6R** (55t) — balanced, mobile, jump jets
- **Marauder MAD-3R** (75t) — dual PPC fire support
- **Atlas AS7-D** (100t) — assault class, all ranges

## Running Tests

```bash
python -m pytest tests/ -v
# or
python tests/test_combat.py
```

## Architecture

- `battletech/weapons.py` — weapon database
- `battletech/tables.py` — hit location, cluster, crit, structure tables
- `battletech/mech.py` — mech data model + damage application
- `battletech/combat.py` — to-hit calculation + attack resolution
- `battletech/heat.py` — heat tracking + effects
- `battletech/simulator.py` — combat loop + Monte Carlo runner
- `data/mechs.json` — mech definitions
