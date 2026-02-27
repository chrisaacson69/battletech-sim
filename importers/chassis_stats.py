"""TT walk_mp lookup by chassis variant name.

HBS TopSpeed doesn't convert cleanly to tabletop movement points,
so this is a manually maintained table based on canonical TT data.

Keyed by chassis VariantName (e.g., "AS7-D", "HBK-4G").
"""

# variant_name -> TT walk_mp
WALK_MP: dict[str, int] = {
    # Light (20-35 tons)
    "LCT-1V":    8,
    "LCT-1M":    8,
    "LCT-1S":    8,
    "COM-1B":    6,
    "COM-2D":    6,
    "SDR-5V":    8,
    "UM-R60":    2,
    "JR7-D":     7,
    "PNT-9R":    4,
    "FS9-H":     6,
    # Medium (40-55 tons)
    "CDA-2A":    8,
    "CDA-3C":    8,
    "BJ-1":      4,
    "VND-1R":    4,
    "CN9-A":     4,
    "CN9-AL":    4,
    "ENF-4R":    4,
    "HBK-4G":    4,
    "HBK-4P":    4,
    "TBT-5N":    5,
    "GRF-1N":    5,
    "GRF-1S":    5,
    "KTO-18":    5,
    "SHD-2D":    5,
    "SHD-2H":    5,
    "WVR-6K":    5,
    "WVR-6R":    5,
    # Heavy (60-75 tons)
    "DRG-1N":    5,
    "QKD-4G":    5,
    "QKD-5A":    5,
    "CPLT-C1":   4,
    "CPLT-K2":   4,
    "JM6-A":     4,
    "JM6-S":     4,
    "TDR-5S":    4,
    "TDR-5SE":   4,
    "TDR-5SS":   4,
    "CTF-1X":    4,
    "GHR-5H":    4,
    "BL-6-KNT":  4,
    "ON1-K":     4,
    "ON1-V":     4,
    # Assault (80-100 tons)
    "AWS-8Q":    3,
    "AWS-8T":    3,
    "VTR-9B":    4,
    "VTR-9S":    4,
    "ZEU-6S":    4,
    "BLR-1G":    4,
    "STK-3F":    3,
    "HGN-733":   4,
    "HGN-733P":  4,
    "BNC-3E":    3,
    "BNC-3M":    3,
    "AS7-D":     3,
    "KGC-0000":  3,
}

# TT jump_mp for variants that can jump.
# If not listed here, jump_mp is derived from JumpJet component count.
# This table is only needed for overrides where component count is wrong.
JUMP_MP_OVERRIDES: dict[str, int] = {}
