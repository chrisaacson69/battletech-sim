"""BattleTech standard tables: hit location, cluster hits, criticals, internal structure."""

import random

# =============================================================================
# Hit Location Tables (2d6)
# Keys are the 2d6 result (2-12), values are location IDs.
# =============================================================================

FRONT_HIT_TABLE: dict[int, str] = {
    2:  "CT",
    3:  "RA",
    4:  "RA",
    5:  "RL",
    6:  "RT",
    7:  "CT",
    8:  "LT",
    9:  "LL",
    10: "LA",
    11: "LA",
    12: "HD",
}

LEFT_SIDE_HIT_TABLE: dict[int, str] = {
    2:  "LT",
    3:  "LL",
    4:  "LA",
    5:  "LA",
    6:  "LL",
    7:  "LT",
    8:  "CT",
    9:  "RT",
    10: "RA",
    11: "RL",
    12: "HD",
}

RIGHT_SIDE_HIT_TABLE: dict[int, str] = {
    2:  "RT",
    3:  "RL",
    4:  "RA",
    5:  "RA",
    6:  "RL",
    7:  "RT",
    8:  "CT",
    9:  "LT",
    10: "LA",
    11: "LL",
    12: "HD",
}

REAR_HIT_TABLE: dict[int, str] = {
    2:  "CT",
    3:  "RT",
    4:  "RT",
    5:  "RL",
    6:  "RT",
    7:  "CT",
    8:  "LT",
    9:  "LL",
    10: "LT",
    11: "LT",
    12: "HD",
}

HIT_TABLES = {
    "front": FRONT_HIT_TABLE,
    "left":  LEFT_SIDE_HIT_TABLE,
    "right": RIGHT_SIDE_HIT_TABLE,
    "rear":  REAR_HIT_TABLE,
}


def roll_2d6() -> int:
    return random.randint(1, 6) + random.randint(1, 6)


def roll_hit_location(direction: str = "front") -> str:
    """Roll 2d6 on the appropriate hit location table."""
    table = HIT_TABLES[direction]
    return table[roll_2d6()]


# =============================================================================
# Cluster Hits Table
# Maps (cluster_size, 2d6_roll) → number of missiles that hit.
# Standard BT cluster table from the rulebook.
# =============================================================================

# Row format: {2d6_roll: missiles_hitting}
# Columns: 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
CLUSTER_TABLE: dict[int, dict[int, int]] = {
    2: {
        2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 2, 9: 2, 10: 2, 11: 2, 12: 2,
    },
    4: {
        2: 1, 3: 1, 4: 2, 5: 2, 6: 2, 7: 3, 8: 3, 9: 3, 10: 3, 11: 4, 12: 4,
    },
    5: {
        2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 3, 8: 3, 9: 4, 10: 4, 11: 5, 12: 5,
    },
    6: {
        2: 2, 3: 2, 4: 3, 5: 3, 6: 4, 7: 4, 8: 4, 9: 4, 10: 5, 11: 5, 12: 6,
    },
    10: {
        2: 3, 3: 3, 4: 4, 5: 6, 6: 6, 7: 6, 8: 6, 9: 8, 10: 8, 11: 10, 12: 10,
    },
    15: {
        2: 5, 3: 5, 4: 6, 5: 9, 6: 9, 7: 9, 8: 9, 9: 12, 10: 12, 11: 15, 12: 15,
    },
    20: {
        2: 6, 3: 6, 4: 9, 5: 12, 6: 12, 7: 12, 8: 12, 9: 16, 10: 16, 11: 20, 12: 20,
    },
}


def roll_cluster_hits(cluster_size: int) -> int:
    """Roll on the cluster table to determine how many missiles hit."""
    if cluster_size not in CLUSTER_TABLE:
        # For sizes not in the table, find the nearest valid size
        valid_sizes = sorted(CLUSTER_TABLE.keys())
        best = min(valid_sizes, key=lambda s: abs(s - cluster_size))
        table = CLUSTER_TABLE[best]
    else:
        table = CLUSTER_TABLE[cluster_size]
    return table[roll_2d6()]


# =============================================================================
# Critical Hits Table (2d6)
# Roll when internal structure is exposed (armor = 0 and damage hits structure).
# =============================================================================

CRIT_TABLE: dict[int, int] = {
    2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0,
    8: 1, 9: 1,
    10: 2, 11: 2,
    12: 3,  # head/limb destroyed
}


def roll_critical_hits() -> int:
    """Roll 2d6 to determine number of critical hits."""
    return CRIT_TABLE[roll_2d6()]


# =============================================================================
# Standard Internal Structure by Tonnage
# =============================================================================

# {tonnage: {location: structure_points}}
INTERNAL_STRUCTURE: dict[int, dict[str, int]] = {
    20: {"HD": 3, "CT": 6,  "LT": 5, "RT": 5, "LA": 3, "RA": 3, "LL": 4, "RL": 4},
    25: {"HD": 3, "CT": 8,  "LT": 6, "RT": 6, "LA": 4, "RA": 4, "LL": 6, "RL": 6},
    30: {"HD": 3, "CT": 10, "LT": 7, "RT": 7, "LA": 5, "RA": 5, "LL": 7, "RL": 7},
    35: {"HD": 3, "CT": 11, "LT": 8, "RT": 8, "LA": 6, "RA": 6, "LL": 8, "RL": 8},
    40: {"HD": 3, "CT": 12, "LT": 10, "RT": 10, "LA": 6, "RA": 6, "LL": 10, "RL": 10},
    45: {"HD": 3, "CT": 14, "LT": 11, "RT": 11, "LA": 7, "RA": 7, "LL": 11, "RL": 11},
    50: {"HD": 3, "CT": 16, "LT": 12, "RT": 12, "LA": 8, "RA": 8, "LL": 12, "RL": 12},
    55: {"HD": 3, "CT": 18, "LT": 13, "RT": 13, "LA": 9, "RA": 9, "LL": 13, "RL": 13},
    60: {"HD": 3, "CT": 20, "LT": 14, "RT": 14, "LA": 10, "RA": 10, "LL": 14, "RL": 14},
    65: {"HD": 3, "CT": 21, "LT": 15, "RT": 15, "LA": 10, "RA": 10, "LL": 15, "RL": 15},
    70: {"HD": 3, "CT": 22, "LT": 15, "RT": 15, "LA": 11, "RA": 11, "LL": 15, "RL": 15},
    75: {"HD": 3, "CT": 23, "LT": 16, "RT": 16, "LA": 12, "RA": 12, "LL": 16, "RL": 16},
    80: {"HD": 3, "CT": 25, "LT": 17, "RT": 17, "LA": 13, "RA": 13, "LL": 17, "RL": 17},
    85: {"HD": 3, "CT": 27, "LT": 18, "RT": 18, "LA": 14, "RA": 14, "LL": 18, "RL": 18},
    90: {"HD": 3, "CT": 29, "LT": 19, "RT": 19, "LA": 15, "RA": 15, "LL": 19, "RL": 19},
    95: {"HD": 3, "CT": 30, "LT": 20, "RT": 20, "LA": 16, "RA": 16, "LL": 20, "RL": 20},
    100: {"HD": 3, "CT": 31, "LT": 21, "RT": 21, "LA": 17, "RA": 17, "LL": 21, "RL": 21},
}


# Damage transfer map: when a location is destroyed, remaining damage goes here.
TRANSFER_MAP: dict[str, str | None] = {
    "HD": None,     # head destroyed = dead, no transfer
    "CT": None,     # CT destroyed = dead, no transfer
    "LT": "CT",
    "RT": "CT",
    "LA": "LT",
    "RA": "RT",
    "LL": "LT",
    "RL": "RT",
}

# Locations that have rear armor
REAR_ARMOR_LOCATIONS = {"CT", "LT", "RT"}

# Movement modifier table: hexes moved → TMM
TARGET_MOVEMENT_MODIFIERS: list[tuple[int, int, int]] = [
    # (min_hexes, max_hexes, modifier)
    (0, 2, 0),
    (3, 4, 1),
    (5, 6, 2),
    (7, 9, 3),
    (10, 17, 4),
    (18, 24, 5),
    (25, 99, 6),
]


def get_target_movement_modifier(hexes_moved: int) -> int:
    """Look up the target movement modifier for a given number of hexes moved."""
    for min_h, max_h, mod in TARGET_MOVEMENT_MODIFIERS:
        if min_h <= hexes_moved <= max_h:
            return mod
    return 6  # max modifier for extreme movement
