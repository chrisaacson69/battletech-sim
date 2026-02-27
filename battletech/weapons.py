"""Weapon database for standard BattleTech weapons."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Weapon:
    name: str
    damage: int            # total damage (for non-cluster) or per-missile (for cluster)
    heat: int
    min_range: int         # 0 = no minimum range
    short_range: int
    medium_range: int
    long_range: int
    ammo_per_ton: int | None   # None for energy weapons
    cluster_size: int = 0      # number of missiles (0 = not a cluster weapon)
    damage_per_missile: int = 0
    is_streak: bool = False    # Streak SRMs: all-or-nothing
    is_ultra: bool = False     # Ultra ACs: can fire twice (jam on 2)
    is_lb_x: bool = False      # LB-X ACs: can fire cluster
    target_heat: int = 0       # heat added to target on hit (flamers)
    tonnage: float = 0         # weapon weight in tons
    crit_slots: int = 1        # critical hit slots occupied (TT standard)


# === Energy Weapons ===

SMALL_LASER = Weapon(
    name="Small Laser", damage=3, heat=1,
    min_range=0, short_range=1, medium_range=2, long_range=3,
    ammo_per_ton=None, tonnage=0.5,
)

MEDIUM_LASER = Weapon(
    name="Medium Laser", damage=5, heat=3,
    min_range=0, short_range=3, medium_range=6, long_range=9,
    ammo_per_ton=None, tonnage=1,
)

LARGE_LASER = Weapon(
    name="Large Laser", damage=8, heat=8,
    min_range=0, short_range=5, medium_range=10, long_range=15,
    ammo_per_ton=None, tonnage=5, crit_slots=2,
)

PPC = Weapon(
    name="PPC", damage=10, heat=10,
    min_range=3, short_range=6, medium_range=12, long_range=18,
    ammo_per_ton=None, tonnage=7, crit_slots=3,
)

ER_LARGE_LASER = Weapon(
    name="ER Large Laser", damage=8, heat=12,
    min_range=0, short_range=7, medium_range=14, long_range=19,
    ammo_per_ton=None, tonnage=5, crit_slots=2,
)

ER_PPC = Weapon(
    name="ER PPC", damage=10, heat=15,
    min_range=0, short_range=7, medium_range=14, long_range=23,
    ammo_per_ton=None, tonnage=7, crit_slots=3,
)

SMALL_PULSE_LASER = Weapon(
    name="Small Pulse Laser", damage=3, heat=2,
    min_range=0, short_range=1, medium_range=2, long_range=3,
    ammo_per_ton=None, tonnage=1,
)

MEDIUM_PULSE_LASER = Weapon(
    name="Medium Pulse Laser", damage=6, heat=4,
    min_range=0, short_range=2, medium_range=4, long_range=6,
    ammo_per_ton=None, tonnage=2,
)

LARGE_PULSE_LASER = Weapon(
    name="Large Pulse Laser", damage=9, heat=10,
    min_range=0, short_range=3, medium_range=7, long_range=10,
    ammo_per_ton=None, tonnage=7, crit_slots=2,
)

FLAMER = Weapon(
    name="Flamer", damage=2, heat=3,
    min_range=0, short_range=1, medium_range=2, long_range=3,
    ammo_per_ton=None, target_heat=2, tonnage=1,
)


# === Ballistic Weapons ===

AC2 = Weapon(
    name="AC/2", damage=2, heat=1,
    min_range=4, short_range=8, medium_range=16, long_range=24,
    ammo_per_ton=45, tonnage=6,
)

AC5 = Weapon(
    name="AC/5", damage=5, heat=1,
    min_range=3, short_range=6, medium_range=12, long_range=18,
    ammo_per_ton=20, tonnage=8, crit_slots=4,
)

AC10 = Weapon(
    name="AC/10", damage=10, heat=3,
    min_range=0, short_range=5, medium_range=10, long_range=15,
    ammo_per_ton=10, tonnage=12, crit_slots=7,
)

AC20 = Weapon(
    name="AC/20", damage=20, heat=7,
    min_range=0, short_range=3, medium_range=6, long_range=9,
    ammo_per_ton=5, tonnage=14, crit_slots=10,
)

ULTRA_AC5 = Weapon(
    name="Ultra AC/5", damage=5, heat=1,
    min_range=2, short_range=6, medium_range=12, long_range=18,
    ammo_per_ton=20, is_ultra=True, tonnage=9, crit_slots=5,
)

LBX_AC10 = Weapon(
    name="LB 10-X AC", damage=10, heat=2,
    min_range=0, short_range=6, medium_range=12, long_range=18,
    ammo_per_ton=10, is_lb_x=True,
    cluster_size=10, damage_per_missile=1, tonnage=11, crit_slots=6,
)

MACHINE_GUN = Weapon(
    name="Machine Gun", damage=2, heat=0,
    min_range=0, short_range=1, medium_range=2, long_range=3,
    ammo_per_ton=200, tonnage=0.5,
)


# === Missile Weapons ===

SRM2 = Weapon(
    name="SRM-2", damage=2, heat=2,
    min_range=0, short_range=3, medium_range=6, long_range=9,
    ammo_per_ton=50, cluster_size=2, damage_per_missile=2, tonnage=1,
)

SRM4 = Weapon(
    name="SRM-4", damage=2, heat=3,
    min_range=0, short_range=3, medium_range=6, long_range=9,
    ammo_per_ton=25, cluster_size=4, damage_per_missile=2, tonnage=2,
)

SRM6 = Weapon(
    name="SRM-6", damage=2, heat=4,
    min_range=0, short_range=3, medium_range=6, long_range=9,
    ammo_per_ton=15, cluster_size=6, damage_per_missile=2, tonnage=3, crit_slots=2,
)

LRM5 = Weapon(
    name="LRM-5", damage=1, heat=2,
    min_range=6, short_range=7, medium_range=14, long_range=21,
    ammo_per_ton=24, cluster_size=5, damage_per_missile=1, tonnage=2,
)

LRM10 = Weapon(
    name="LRM-10", damage=1, heat=4,
    min_range=6, short_range=7, medium_range=14, long_range=21,
    ammo_per_ton=12, cluster_size=10, damage_per_missile=1, tonnage=5, crit_slots=2,
)

LRM15 = Weapon(
    name="LRM-15", damage=1, heat=5,
    min_range=6, short_range=7, medium_range=14, long_range=21,
    ammo_per_ton=8, cluster_size=15, damage_per_missile=1, tonnage=7, crit_slots=3,
)

LRM20 = Weapon(
    name="LRM-20", damage=1, heat=6,
    min_range=6, short_range=7, medium_range=14, long_range=21,
    ammo_per_ton=6, cluster_size=20, damage_per_missile=1, tonnage=10, crit_slots=5,
)

STREAK_SRM2 = Weapon(
    name="Streak SRM-2", damage=2, heat=2,
    min_range=0, short_range=3, medium_range=6, long_range=9,
    ammo_per_ton=50, cluster_size=2, damage_per_missile=2,
    is_streak=True, tonnage=1.5,
)

STREAK_SRM4 = Weapon(
    name="Streak SRM-4", damage=2, heat=3,
    min_range=0, short_range=3, medium_range=6, long_range=9,
    ammo_per_ton=25, cluster_size=4, damage_per_missile=2,
    is_streak=True, tonnage=3,
)

STREAK_SRM6 = Weapon(
    name="Streak SRM-6", damage=2, heat=4,
    min_range=0, short_range=3, medium_range=6, long_range=9,
    ammo_per_ton=15, cluster_size=6, damage_per_missile=2,
    is_streak=True, tonnage=4.5, crit_slots=2,
)


# Lookup by name for JSON loading
WEAPON_DB: dict[str, Weapon] = {w.name: w for w in [
    SMALL_LASER, MEDIUM_LASER, LARGE_LASER, PPC,
    ER_LARGE_LASER, ER_PPC,
    SMALL_PULSE_LASER, MEDIUM_PULSE_LASER, LARGE_PULSE_LASER,
    FLAMER,
    AC2, AC5, AC10, AC20,
    ULTRA_AC5, LBX_AC10, MACHINE_GUN,
    SRM2, SRM4, SRM6,
    LRM5, LRM10, LRM15, LRM20,
    STREAK_SRM2, STREAK_SRM4, STREAK_SRM6,
]}
