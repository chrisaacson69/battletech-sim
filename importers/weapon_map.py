"""Mapping from HBS ComponentDefIDs to WEAPON_DB names.

HBS weapon IDs follow the pattern:
    Weapon_{Category}_{Type}_{N}-{Manufacturer}

We strip the _{N}-{Manufacturer} suffix to get the base weapon type,
then map to our WEAPON_DB name. Weapons not in WEAPON_DB map to None
and are skipped during import with a warning.
"""

import re


def _extract_base_type(component_def_id: str) -> str:
    """Strip the _N-Manufacturer suffix from an HBS weapon ComponentDefID.

    Examples:
        Weapon_Laser_MediumLaser_0-STOCK -> Weapon_Laser_MediumLaser
        Weapon_PPC_PPC_2-Tiegart        -> Weapon_PPC_PPC
        Weapon_LRM_LRM20_2-Delta        -> Weapon_LRM_LRM20
    """
    return re.sub(r"_\d+.*$", "", component_def_id)


# Base type -> WEAPON_DB name (or None if not supported)
_BASE_TYPE_MAP: dict[str, str | None] = {
    # Energy
    "Weapon_Laser_SmallLaser":       "Small Laser",
    "Weapon_Laser_MediumLaser":      "Medium Laser",
    "Weapon_Laser_LargeLaser":       "Large Laser",
    "Weapon_Laser_SmallLaserER":     None,            # ER Small Laser not in WEAPON_DB
    "Weapon_Laser_MediumLaserER":    None,            # ER Medium Laser not in WEAPON_DB
    "Weapon_Laser_LargeLaserER":     "ER Large Laser",
    "Weapon_Laser_SmallLaserPulse":  "Small Pulse Laser",
    "Weapon_Laser_MediumLaserPulse": "Medium Pulse Laser",
    "Weapon_Laser_LargeLaserPulse":  "Large Pulse Laser",
    "Weapon_PPC_PPC":                "PPC",
    "Weapon_PPC_PPCER":              "ER PPC",
    "Weapon_Flamer_Flamer":          "Flamer",
    # Ballistic
    "Weapon_Autocannon_AC2":         "AC/2",
    "Weapon_Autocannon_AC5":         "AC/5",
    "Weapon_Autocannon_AC10":        "AC/10",
    "Weapon_Autocannon_AC20":        "AC/20",
    "Weapon_MachineGun_MachineGun":  "Machine Gun",
    "Weapon_Gauss_Gauss":            None,            # Gauss not in WEAPON_DB
    # Missiles
    "Weapon_LRM_LRM5":              "LRM-5",
    "Weapon_LRM_LRM10":             "LRM-10",
    "Weapon_LRM_LRM15":             "LRM-15",
    "Weapon_LRM_LRM20":             "LRM-20",
    "Weapon_SRM_SRM2":              "SRM-2",
    "Weapon_SRM_SRM4":              "SRM-4",
    "Weapon_SRM_SRM6":              "SRM-6",
}


def map_weapon(component_def_id: str) -> str | None:
    """Map an HBS weapon ComponentDefID to a WEAPON_DB name.

    Returns None if the weapon is not supported (caller should skip with warning).
    """
    base = _extract_base_type(component_def_id)
    if base not in _BASE_TYPE_MAP:
        return None
    return _BASE_TYPE_MAP[base]


# HBS ammo box ID -> weapon type family for ammo distribution.
# "LRM" and "SRM" are generic families that apply to all sizes of that type.
AMMO_MAP: dict[str, str] = {
    "Ammo_AmmunitionBox_Generic_AC2":   "AC/2",
    "Ammo_AmmunitionBox_Generic_AC5":   "AC/5",
    "Ammo_AmmunitionBox_Generic_AC10":  "AC/10",
    "Ammo_AmmunitionBox_Generic_AC20":  "AC/20",
    "Ammo_AmmunitionBox_Generic_LRM":   "LRM",
    "Ammo_AmmunitionBox_Generic_SRM":   "SRM",
    "Ammo_AmmunitionBox_Generic_MG":    "Machine Gun",
    "Ammo_AmmunitionBox_Generic_GAUSS": None,  # Gauss not supported
}


def ammo_matches_weapon(ammo_family: str, weapon_name: str) -> bool:
    """Check if an ammo family matches a weapon name.

    For specific types (AC/2, AC/5, etc.) it's an exact match.
    For generic families (LRM, SRM) it matches any size (LRM-5, LRM-20, etc.).
    """
    if ammo_family == weapon_name:
        return True
    if ammo_family in ("LRM", "SRM") and weapon_name.startswith(ammo_family + "-"):
        return True
    return False
