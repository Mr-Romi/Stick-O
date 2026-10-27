#!/usr/bin/env python3
"""
SHADOW STICKMAN: ECLIPSE DUEL
=============================
A real-time, 30-FPS terminal martial arts fighting game inspired by Shadow Fight.
100% cross-platform (Windows PowerShell/CMD, Linux, macOS) with ZERO external
dependencies! Runs out-of-the-box on Windows without `_curses` or `windows-curses`
by using native `msvcrt` + Windows Console Virtual Terminal ANSI sequences, and
uses `curses` (or ANSI fallback) on Linux/macOS.

Quick Run:
  python shadow_stickman.py          # Interactive terminal game (Windows/Linux/macOS)
  python shadow_stickman.py --demo   # Automated AI vs AI demonstration match
  python shadow_stickman.py --test   # Run built-in self-diagnostic test suite
  python shadow_stickman.py --demo --seed=7   # Reproducible AI vs AI match (any integer seed)

Controls:
  A / D or Left / Right : Move / Dash (press E to Dash)
  W or Up               : Jump (press A/D in air for air control)
  S or Down             : Crouch / Hold to Block (reduces damage by 80%, parries on early frame)
  J                     : Punch (Neutral: Jab, Forward: Cross, Crouch: Uppercut, Air: Flying Kick)
  K                     : Kick  (Neutral: High Kick, Forward: Spinning Roundhouse, Crouch: Low Sweep, Air: Flying Kick)
  L                     : Weapon / Ranged Attack (Katana Slash / Kusarigama Lash or Kunai Throw)
  U                     : Shadow Ability (Costs 50 Shadow Energy: Void Blink / Abyssal Eruption)
  I                     : Unleash Shadow Form (At >=50% Shadow Energy: 1.4x damage, speed boost, lifesteal)
  1 / 2 / 3             : Switch Weapon Style mid-fight (1: Barehanded, 2: Shadow Katana, 3: Blood Kusarigama)
  P                     : Pause / Move List
  Q                     : Quit to Title / Exit
"""

import math
import os
import random
import shutil
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

# Optional curses import (not included in standard Windows Python builds)
try:
    import curses as _curses_mod  # type: ignore
    HAS_CURSES = True
except ImportError:
    _curses_mod = None
    HAS_CURSES = False

# Optional Windows msvcrt / POSIX select import for native terminal input
if os.name == "nt":
    import msvcrt  # type: ignore
    select = None  # type: ignore
else:
    msvcrt = None  # type: ignore
    import select  # type: ignore

# Universal Key Constants (compatible whether curses is installed or not)
KEY_LEFT = _curses_mod.KEY_LEFT if HAS_CURSES else 260
KEY_RIGHT = _curses_mod.KEY_RIGHT if HAS_CURSES else 261
KEY_UP = _curses_mod.KEY_UP if HAS_CURSES else 259
KEY_DOWN = _curses_mod.KEY_DOWN if HAS_CURSES else 258

# ---------------------------------------------------------------------------
# Constants & Physics Tuning
# ---------------------------------------------------------------------------
FPS = 30
FRAME_TIME = 1.0 / FPS
STAGE_WIDTH = 100
STAGE_HEIGHT = 26
GROUND_Y = 20
GRAVITY = 0.55
SHADOW_FORM_DAMAGE_MULT = 1.40  # Applies to melee AND projectiles while Shadow Form is active

# Terminals report key presses / OS auto-repeats, not key-up events, so a held key can show
# gaps of a frame or two. Held-type keys (move/crouch/guard) stay "latched" for this many
# frames after their last event so guard and crouch do not flicker (and re-open the parry window).
HOLD_GRACE_FRAMES = 3
LEFT_KEYS = {ord("a"), ord("A"), KEY_LEFT}
RIGHT_KEYS = {ord("d"), ord("D"), KEY_RIGHT}
HOLD_KEYS = LEFT_KEYS | RIGHT_KEYS | {ord("s"), ord("S"), KEY_DOWN}

# States
STATE_IDLE = "IDLE"
STATE_WALK = "WALK"
STATE_CROUCH = "CROUCH"
STATE_JUMP = "JUMP"
STATE_DASH = "DASH"
STATE_ATTACK = "ATTACK"
STATE_HITSTUN = "HITSTUN"
STATE_KNOCKDOWN = "KNOCKDOWN"
STATE_VICTORY = "VICTORY"
STATE_DEFEAT = "DEFEAT"

# Weapons
WEAPON_FISTS = "Barehanded"
WEAPON_KATANA = "Shadow Katana"
WEAPON_KUSARI = "Blood Kusarigama"


@dataclass
class MoveSpec:
    name: str
    startup: int          # Frames before hitbox becomes active
    active: int           # Frames hitbox stays active
    recovery: int         # Frames after active before returning to idle
    damage: float         # Base health damage
    shadow_gain: float    # Shadow energy earned on hit
    reach_x: int          # Horizontal reach in stage units from fighter center
    reach_y_top: int      # Vertical top offset relative to fighter y (negative = up)
    reach_y_bot: int      # Vertical bottom offset relative to fighter y
    knockback_x: float    # Horizontal velocity applied to defender
    knockback_y: float    # Vertical velocity applied to defender (negative = launch up)
    hitstun: int          # Frames of hitstun
    is_low: bool = False  # Sweeps/lows hit standing guard; require crouch block
    is_overhead: bool = False  # Overheads hit crouching guard; require standing block
    is_high: bool = False  # High attacks whiff completely against a crouching defender
    causes_knockdown: bool = False
    shadow_cost: float = 0.0
    forward_momentum: float = 0.0
    invulnerable_startup: bool = False
    spawns_projectile: bool = False
    pose_startup: str = "windup"
    pose_active: str = "punch"
    pose_recovery: str = "idle"

    @property
    def total_frames(self) -> int:
        return self.startup + self.active + self.recovery


# Comprehensive Martial Arts & Weapon Move Catalog
MOVES: Dict[str, MoveSpec] = {
    # --- Barehanded & Universal Martial Arts ---
    "jab": MoveSpec(
        name="Shadow Jab", startup=2, active=2, recovery=3,
        damage=6.0, shadow_gain=8.0, reach_x=7, reach_y_top=-5, reach_y_bot=-2,
        knockback_x=1.2, knockback_y=0.0, hitstun=5, forward_momentum=0.5,
        pose_startup="windup_punch", pose_active="jab", pose_recovery="idle"
    ),
    "cross": MoveSpec(
        name="Heavy Cross", startup=4, active=3, recovery=5,
        damage=11.0, shadow_gain=14.0, reach_x=9, reach_y_top=-5, reach_y_bot=-2,
        knockback_x=2.6, knockback_y=-0.8, hitstun=8, forward_momentum=1.4,
        pose_startup="windup_punch", pose_active="cross", pose_recovery="idle"
    ),
    "uppercut": MoveSpec(
        name="Rising Dragon Uppercut", startup=4, active=3, recovery=6,
        damage=14.0, shadow_gain=16.0, reach_x=7, reach_y_top=-7, reach_y_bot=-1,
        knockback_x=1.5, knockback_y=-2.8, hitstun=11, causes_knockdown=True,
        forward_momentum=0.8,
        pose_startup="crouch", pose_active="uppercut", pose_recovery="idle"
    ),
    "high_kick": MoveSpec(
        name="Snap High Kick", startup=4, active=3, recovery=5,
        damage=12.0, shadow_gain=14.0, reach_x=10, reach_y_top=-6, reach_y_bot=-2,
        knockback_x=2.4, knockback_y=-0.6, hitstun=8, is_high=True, forward_momentum=0.8,
        pose_startup="windup_kick", pose_active="high_kick", pose_recovery="idle"
    ),
    "roundhouse": MoveSpec(
        name="Spinning Roundhouse", startup=6, active=3, recovery=7,
        damage=18.0, shadow_gain=20.0, reach_x=12, reach_y_top=-6, reach_y_bot=-2,
        knockback_x=4.0, knockback_y=-1.5, hitstun=12, is_high=True, causes_knockdown=True,
        forward_momentum=1.8,
        pose_startup="spin", pose_active="roundhouse", pose_recovery="idle"
    ),
    "sweep": MoveSpec(
        name="Shadow Leg Sweep", startup=4, active=3, recovery=6,
        damage=10.0, shadow_gain=12.0, reach_x=10, reach_y_top=-2, reach_y_bot=0,
        knockback_x=1.0, knockback_y=-1.8, hitstun=12, is_low=True,
        causes_knockdown=True, forward_momentum=1.0,
        pose_startup="crouch", pose_active="sweep", pose_recovery="crouch"
    ),
    "air_kick": MoveSpec(
        name="Flying Shadow Kick", startup=3, active=5, recovery=4,
        damage=14.0, shadow_gain=15.0, reach_x=10, reach_y_top=-5, reach_y_bot=0,
        knockback_x=3.0, knockback_y=-1.0, hitstun=9, is_overhead=True,
        forward_momentum=2.0,
        pose_startup="jump", pose_active="air_kick", pose_recovery="jump"
    ),
    # --- Weapon Attacks ---
    "katana_slash": MoveSpec(
        name="Iaido Crescent Slash", startup=4, active=3, recovery=5,
        damage=16.0, shadow_gain=18.0, reach_x=14, reach_y_top=-6, reach_y_bot=-1,
        knockback_x=2.8, knockback_y=-0.5, hitstun=9, forward_momentum=1.6,
        pose_startup="katana_sheathe", pose_active="katana_slash", pose_recovery="idle"
    ),
    "katana_heavy": MoveSpec(
        name="Helm Splitter (Overhead)", startup=7, active=3, recovery=7,
        damage=22.0, shadow_gain=22.0, reach_x=15, reach_y_top=-8, reach_y_bot=0,
        knockback_x=3.5, knockback_y=-2.0, hitstun=13, is_overhead=True,
        causes_knockdown=True, forward_momentum=2.2,
        pose_startup="katana_high", pose_active="katana_slash", pose_recovery="idle"
    ),
    "kusari_whip": MoveSpec(
        name="Kusarigama Chain Lash", startup=5, active=3, recovery=6,
        damage=15.0, shadow_gain=16.0, reach_x=19, reach_y_top=-6, reach_y_bot=-1,
        knockback_x=3.2, knockback_y=-0.5, hitstun=9, forward_momentum=0.4,
        pose_startup="windup_punch", pose_active="kusari_whip", pose_recovery="idle"
    ),
    "kunai_throw": MoveSpec(
        name="Shadow Kunai", startup=4, active=2, recovery=6,
        damage=8.0, shadow_gain=10.0, reach_x=5, reach_y_top=-5, reach_y_bot=-2,
        knockback_x=1.5, knockback_y=0.0, hitstun=6, spawns_projectile=True,
        pose_startup="windup_punch", pose_active="throw", pose_recovery="idle"
    ),
    # --- Shadow Abilities ---
    "shadow_strike": MoveSpec(
        name="Void Blink Assassination", startup=4, active=4, recovery=6,
        damage=28.0, shadow_gain=0.0, reach_x=16, reach_y_top=-7, reach_y_bot=0,
        knockback_x=4.5, knockback_y=-2.6, hitstun=15, is_overhead=True,
        causes_knockdown=True, shadow_cost=50.0, forward_momentum=3.5,
        invulnerable_startup=True,
        pose_startup="shadow_charge", pose_active="shadow_slash", pose_recovery="idle"
    ),
    "shadow_eruption": MoveSpec(
        name="Abyssal Pillar Eruption", startup=5, active=4, recovery=6,
        damage=26.0, shadow_gain=0.0, reach_x=18, reach_y_top=-9, reach_y_bot=0,
        knockback_x=2.0, knockback_y=-3.5, hitstun=16, is_low=True,
        causes_knockdown=True, shadow_cost=50.0, invulnerable_startup=True,
        pose_startup="crouch", pose_active="shadow_eruption", pose_recovery="idle"
    ),
}


# ---------------------------------------------------------------------------
# Stickman ASCII Pose Art (6 rows tall, 11 columns wide)
# Right-facing templates; automatically mirrored when facing left!
# ---------------------------------------------------------------------------
POSE_ART_RIGHT: Dict[str, List[str]] = {
    "idle": [
        "    (_)    ",
        "   / | \\   ",
        "  /  |  \\  ",
        "     |     ",
        "    / \\    ",
        "   /   \\   ",
    ],
    "walk_1": [
        "    (_)    ",
        "   / | \\   ",
        "  /  |  \\  ",
        "     |     ",
        "    / \\    ",
        "   /   \\_  ",
    ],
    "walk_2": [
        "    (_)    ",
        "   \\ | /   ",
        "    \\|/    ",
        "     |     ",
        "    /|     ",
        "  _/ |_    ",
    ],
    "crouch": [
        "           ",
        "    (_)    ",
        "   / | \\   ",
        "   \\_|_/   ",
        "   /   \\   ",
        " _/     \\_ ",
    ],
    "block": [
        "    (_) ]  ",
        "   / |-[|  ",
        "  |  |  |  ",
        "     |     ",
        "    / \\    ",
        "   /   \\   ",
    ],
    "crouch_block": [
        "           ",
        "    (_) ]  ",
        "   / |-[|  ",
        "   \\_|_/   ",
        "   /   \\   ",
        " _/     \\_ ",
    ],
    "jump": [
        "   \\(_)/   ",
        "    \\|/    ",
        "     |     ",
        "    / \\    ",
        "   \\   /   ",
        "           ",
    ],
    "dash": [
        "     (_)   ",
        "  ==/ | \\  ",
        " ==/  |    ",
        "     /     ",
        "   _/ \\    ",
        "  /    \\   ",
    ],
    "windup_punch": [
        "    (_)    ",
        "  _\\ |     ",
        " (__\\|     ",
        "     |     ",
        "    / \\    ",
        "   /   \\   ",
    ],
    "jab": [
        "    (_)    ",
        "   / |====@",
        "  /  |     ",
        "     |     ",
        "    / \\    ",
        "   /   \\   ",
    ],
    "cross": [
        "     (_)   ",
        "  --/ |===@",
        "      |>>>@",
        "     /     ",
        "    / \\    ",
        "  _/   \\   ",
    ],
    "uppercut": [
        "       ^   ",
        "    (_)|   ",
        "   / |/    ",
        "     |     ",
        "    / \\    ",
        "   /   \\   ",
    ],
    "windup_kick": [
        "    (_)    ",
        "   / | \\   ",
        "     |     ",
        "     |_\\   ",
        "    /      ",
        "   /       ",
    ],
    "high_kick": [
        "    (_)  / ",
        "   / | ==/ ",
        "  /  |/    ",
        "     |     ",
        "    /      ",
        "   /       ",
    ],
    "spin": [
        "   ~(_)~   ",
        "  -- | --  ",
        "    /|\\    ",
        "     |     ",
        "    / \\    ",
        "   /   \\   ",
    ],
    "roundhouse": [
        "    (_)    ",
        "  \\  |====>",
        "   \\ |     ",
        "     |     ",
        "    /      ",
        "  _/       ",
    ],
    "sweep": [
        "           ",
        "           ",
        "   (_)     ",
        "  / | \\    ",
        " /  |__\\==>",
        "   /       ",
    ],
    "air_kick": [
        "    (_)    ",
        "   / | \\   ",
        "     |====>",
        "    /      ",
        "           ",
        "           ",
    ],
    "katana_sheathe": [
        "    (_)    ",
        "   / | \\   ",
        "  /==|==\\  ",
        "     |     ",
        "    / \\    ",
        "   /   \\   ",
    ],
    "katana_high": [
        "    (_) // ",
        "   / | //  ",
        "     |//   ",
        "     |     ",
        "    / \\    ",
        "   /   \\   ",
    ],
    "katana_slash": [
        "     (_)   ",
        "   / |====/",
        "  /  |   / ",
        "     |  /  ",
        "    / \\    ",
        "  _/   \\   ",
    ],
    "kusari_whip": [
        "    (_)    ",
        "   / |~~~~~",
        "  /  |     ",
        "     |     ",
        "    / \\    ",
        "   /   \\   ",
    ],
    "throw": [
        "    (_)    ",
        "   / |--->>",
        "  /  |     ",
        "     |     ",
        "    / \\    ",
        "   /   \\   ",
    ],
    "shadow_charge": [
        "  * (_) *  ",
        " * \\ | / * ",
        "  * \\|/ *  ",
        "   * | *   ",
        "    / \\    ",
        "   /   \\   ",
    ],
    "shadow_slash": [
        "  *  (_)   ",
        " * / |#####",
        "  *  |#####",
        "     |     ",
        "    / \\    ",
        "  _/   \\   ",
    ],
    "shadow_eruption": [
        "   ^ ^ ^   ",
        "  ||(_)||  ",
        "  ||\\|/||  ",
        "  ||| |||  ",
        "  ||/ \\||  ",
        "  |/   \\|  ",
    ],
    "hitstun": [
        "   (_)!    ",
        "  \\ | /    ",
        "   \\|/     ",
        "    |      ",
        "   / \\     ",
        "  /   \\    ",
    ],
    "knockdown": [
        "           ",
        "           ",
        "           ",
        "           ",
        "  _        ",
        " (_)==/\\/\\ ",
    ],
    "victory": [
        "   \\(_)/   ",
        "    \\|/    ",
        "     |     ",
        "     |     ",
        "    / \\    ",
        "   /   \\   ",
    ],
}

MIRROR_CHAR_MAP = str.maketrans({
    "/": "\\",
    "\\": "/",
    "(": ")",
    ")": "(",
    "[": "]",
    "]": "[",
    "<": ">",
    ">": "<",
})


def get_pose_lines(pose_name: str, facing: int) -> List[str]:
    """Return 6-line stickman sprite oriented in `facing` (+1 right, -1 left)."""
    lines = POSE_ART_RIGHT.get(pose_name, POSE_ART_RIGHT["idle"])
    if facing >= 0:
        return lines
    return [line[::-1].translate(MIRROR_CHAR_MAP) for line in lines]


# ---------------------------------------------------------------------------
# Visual FX: Particles, Hit Sparks, Floating Texts, Kunai Projectiles
# ---------------------------------------------------------------------------
@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    char: str
    color_pair: int
    ttl: int


@dataclass
class FloatingText:
    x: float
    y: float
    text: str
    color_pair: int
    ttl: int


@dataclass
class Projectile:
    owner_id: int
    x: float
    y: float
    vx: float
    damage: float
    shadow_gain: float
    ttl: int = 35
    active: bool = True


@dataclass
class HitPlan:
    """A fully evaluated contact (melee or projectile), decided BEFORE any state is mutated."""
    attacker: "Fighter"
    defender: "Fighter"
    kind: str                 # "parry", "block" or "hit"
    damage: float
    shadow_gain: float
    knockback_x: float
    knockback_y: float
    hitstun: int
    causes_knockdown: bool
    push_dir: int
    hit_x: float
    hit_y: float
    is_counter: bool = False
    is_projectile: bool = False
    shadowy: bool = False     # Shadow abilities get shadow-colored sparks


# ---------------------------------------------------------------------------
# Fighter Class
# ---------------------------------------------------------------------------
class Fighter:
    def __init__(
        self,
        fighter_id: int,
        name: str,
        x: float,
        facing: int,
        is_ai: bool = False,
        weapon: str = WEAPON_KATANA,
    ):
        self.fighter_id = fighter_id
        self.name = name
        self.x = x
        self.y = float(GROUND_Y)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = facing
        self.is_ai = is_ai
        self.weapon = weapon

        self.max_hp = 100.0
        self.hp = 100.0
        self.max_shadow = 100.0
        self.shadow = 25.0
        self.shadow_form = False
        self.shadow_form_timer = 0

        self.state = STATE_IDLE
        self.state_timer = 0
        self.blocking = False
        self.block_frames = 0

        self.current_move: Optional[MoveSpec] = None
        self.move_frame = 0
        self.move_has_hit = False

        self.combo_count = 0
        self.combo_timer = 0
        self.last_move_name = ""
        self.rounds_won = 0
        self.walk_cycle = 0

        # AI state tracking
        self.ai_cooldown = 0
        self.ai_aggression = 0.65

    def reset_for_round(self, x: float, facing: int) -> None:
        self.x = x
        self.y = float(GROUND_Y)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = facing
        self.hp = self.max_hp
        self.shadow = max(25.0, min(self.max_shadow, self.shadow))
        self.shadow_form = False
        self.shadow_form_timer = 0
        self.state = STATE_IDLE
        self.state_timer = 0
        self.blocking = False
        self.block_frames = 0
        self.current_move = None
        self.move_frame = 0
        self.move_has_hit = False
        self.combo_count = 0
        self.combo_timer = 0

    @property
    def on_ground(self) -> bool:
        return self.y >= GROUND_Y - 0.01

    @property
    def can_act(self) -> bool:
        return self.state in (STATE_IDLE, STATE_WALK, STATE_CROUCH, STATE_JUMP)

    def activate_shadow_form(self) -> bool:
        if self.shadow >= 50.0 and not self.shadow_form and self.state not in (STATE_HITSTUN, STATE_KNOCKDOWN):
            self.shadow_form = True
            return True
        return False

    def start_move(self, move_key: str) -> bool:
        move = MOVES[move_key]
        if self.shadow < move.shadow_cost:
            return False

        # Allow combo cancel from jab into cross/uppercut/high_kick/weapon strikes on hit
        can_cancel = (
            self.state == STATE_ATTACK
            and self.current_move is not None
            and self.current_move.name == "Shadow Jab"
            and self.move_has_hit
            and move_key in ("cross", "uppercut", "high_kick", "katana_slash", "kusari_whip")
        )
        if not self.can_act and not can_cancel:
            return False

        self.shadow -= move.shadow_cost
        self.state = STATE_ATTACK
        self.current_move = move
        self.move_frame = 0
        self.move_has_hit = False
        self.blocking = False
        self.last_move_name = move.name

        speed_mult = 1.35 if self.shadow_form else 1.0
        self.vx = self.facing * move.forward_momentum * speed_mult
        return True

    def start_dash(self, direction: int) -> bool:
        if not self.can_act or not self.on_ground:
            return False
        self.state = STATE_DASH
        self.state_timer = 5
        self.blocking = False
        speed = 3.2 if self.shadow_form else 2.5
        self.vx = direction * speed
        return True

    def get_hurtbox(self) -> Tuple[float, float, float, float]:
        """Return (x_min, y_top, x_max, y_bottom) in stage coordinates."""
        if self.state == STATE_KNOCKDOWN:
            return (self.x - 4, self.y - 2, self.x + 4, self.y)
        if self.state == STATE_CROUCH:
            return (self.x - 2.5, self.y - 4, self.x + 2.5, self.y)
        return (self.x - 2.5, self.y - 6, self.x + 2.5, self.y)

    def get_active_hitbox(self) -> Optional[Tuple[float, float, float, float]]:
        """Return (x_min, y_top, x_max, y_bottom) if currently in active attack frames."""
        if self.state != STATE_ATTACK or self.current_move is None:
            return None
        m = self.current_move
        if m.spawns_projectile:
            return None
        if m.startup <= self.move_frame < m.startup + m.active:
            if self.facing >= 0:
                x1 = self.x + 1.0
                x2 = self.x + m.reach_x
            else:
                x1 = self.x - m.reach_x
                x2 = self.x - 1.0
            y1 = self.y + m.reach_y_top
            y2 = self.y + m.reach_y_bot
            return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        return None

    def is_invulnerable(self) -> bool:
        if self.state == STATE_KNOCKDOWN and self.state_timer > 3:
            return True
        # state_timer is decremented before hit checks, so >= 2 gives exactly 3 invulnerable frames
        if self.state == STATE_DASH and self.state_timer >= 2:
            return True
        if (
            self.state == STATE_ATTACK
            and self.current_move is not None
            and self.current_move.invulnerable_startup
            and self.move_frame < self.current_move.startup
        ):
            return True
        return False

    def get_current_pose(self) -> str:
        if self.state == STATE_VICTORY:
            return "victory"
        if self.state in (STATE_KNOCKDOWN, STATE_DEFEAT):
            return "knockdown"
        if self.state == STATE_HITSTUN:
            return "hitstun"
        if self.state == STATE_DASH:
            return "dash"
        if self.state == STATE_ATTACK and self.current_move is not None:
            m = self.current_move
            if self.move_frame < m.startup:
                return m.pose_startup
            elif self.move_frame < m.startup + m.active:
                return m.pose_active
            else:
                return m.pose_recovery
        if not self.on_ground:
            return "jump"
        if self.blocking:
            return "crouch_block" if self.state == STATE_CROUCH else "block"
        if self.state == STATE_CROUCH:
            return "crouch"
        if self.state == STATE_WALK:
            return "walk_1" if (self.walk_cycle // 3) % 2 == 0 else "walk_2"
        return "idle"


# ---------------------------------------------------------------------------
# Core Game Engine & State Machine
# ---------------------------------------------------------------------------
class ShadowFightEngine:
    def __init__(self, ai_difficulty: int = 2, p1_is_ai: bool = False):
        self.ai_difficulty = ai_difficulty
        self.p1 = Fighter(1, "SHADOW RONIN", 28.0, +1, is_ai=p1_is_ai, weapon=WEAPON_KATANA)
        self.p2 = Fighter(2, "ECLIPSE SHOGUN", 72.0, -1, is_ai=True, weapon=WEAPON_KUSARI)
        self.projectiles: List[Projectile] = []
        self.particles: List[Particle] = []
        self.floating_texts: List[FloatingText] = []

        self.round_num = 1
        self.round_timer = 99 * FPS
        self.round_over = False
        self.round_over_timer = 0
        self.match_winner: Optional[Fighter] = None
        self.screen_shake = 0
        self.hitstop_frames = 0
        self.announcer_text = "ROUND 1 - FIGHT!"
        self.announcer_timer = 45
        self.paused = False

        # Private RNG for the fixed starfield so the global RNG (AI, particles) is never reseeded
        star_rng = random.Random(42)
        self.stars = [(star_rng.randint(2, STAGE_WIDTH - 3), star_rng.randint(1, 9)) for _ in range(28)]

        self.buffered_keys: Set[int] = set()   # Presses made during hitstop, replayed afterwards
        self.hold_age: Dict[int, int] = {}     # Frames since each held-type key was last seen

    def start_next_round(self) -> None:
        self.round_num += 1
        self.p1.reset_for_round(28.0, +1)
        self.p2.reset_for_round(72.0, -1)
        self.projectiles.clear()
        self.particles.clear()
        self.floating_texts.clear()
        self.round_timer = 99 * FPS
        self.round_over = False
        self.round_over_timer = 0
        self.announcer_text = f"ROUND {self.round_num} - FIGHT!"
        self.announcer_timer = 45
        self.hitstop_frames = 0
        self.screen_shake = 0
        self.buffered_keys = set()
        self.hold_age = {}

    def reset_match(self, p1_is_ai: bool = False) -> None:
        self.p1 = Fighter(1, "SHADOW RONIN", 28.0, +1, is_ai=p1_is_ai, weapon=WEAPON_KATANA)
        self.p2 = Fighter(2, "ECLIPSE SHOGUN", 72.0, -1, is_ai=True, weapon=WEAPON_KUSARI)
        self.round_num = 0
        self.match_winner = None
        self.paused = False
        self.start_next_round()

    def spawn_hit_sparks(self, x: float, y: float, count: int, color_pair: int, heavy: bool = False) -> None:
        chars = ["*", "+", "x", "."] if not heavy else ["#", "*", "@", "+", "!"]
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(0.4, 2.2 if heavy else 1.3)
            self.particles.append(
                Particle(
                    x=x,
                    y=y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed * 0.6 - 0.2,
                    char=random.choice(chars),
                    color_pair=color_pair,
                    ttl=random.randint(5, 11),
                )
            )

    def add_floating_text(self, x: float, y: float, text: str, color_pair: int) -> None:
        self.floating_texts.append(FloatingText(x=x, y=y, text=text, color_pair=color_pair, ttl=18))

    def process_player_input(self, f: Fighter, opponent: Fighter, keys: Set[int]) -> None:
        """Apply keyboard actions to Fighter `f`."""
        if self.round_over:
            return

        # Weapon style switching
        if ord("1") in keys:
            f.weapon = WEAPON_FISTS
            self.add_floating_text(f.x, f.y - 7, "STYLE: BAREHANDED", 4)
        elif ord("2") in keys:
            f.weapon = WEAPON_KATANA
            self.add_floating_text(f.x, f.y - 7, "STYLE: KATANA", 4)
        elif ord("3") in keys:
            f.weapon = WEAPON_KUSARI
            self.add_floating_text(f.x, f.y - 7, "STYLE: KUSARIGAMA", 4)

        # Shadow Form activation
        if ord("i") in keys or ord("I") in keys:
            if f.activate_shadow_form():
                self.add_floating_text(f.x, f.y - 8, "SHADOW FORM UNLEASHED!", 5)
                self.spawn_hit_sparks(f.x, f.y - 3, 16, 5, heavy=True)
                self.screen_shake = 4

        move_left = (ord("a") in keys or ord("A") in keys or KEY_LEFT in keys)
        move_right = (ord("d") in keys or ord("D") in keys or KEY_RIGHT in keys)
        crouch = (ord("s") in keys or ord("S") in keys or KEY_DOWN in keys)
        jump = (ord("w") in keys or ord("W") in keys or KEY_UP in keys)
        dash_key = (ord("e") in keys or ord("E") in keys)

        forward_held = (move_right and f.facing > 0) or (move_left and f.facing < 0)
        backward_held = (move_left and f.facing > 0) or (move_right and f.facing < 0)

        # Shadow ability (U)
        if ord("u") in keys or ord("U") in keys:
            if not f.on_ground:
                pass  # Ground abilities require footing
            else:
                ability = "shadow_eruption" if crouch else "shadow_strike"
                if f.start_move(ability):
                    if ability == "shadow_strike":
                        target_x = opponent.x - f.facing * 10.0
                        f.x = max(6.0, min(STAGE_WIDTH - 6.0, (f.x + target_x) * 0.5))
                    self.spawn_hit_sparks(f.x, f.y - 3, 12, 5, heavy=True)
                    self.add_floating_text(f.x, f.y - 8, MOVES[ability].name.upper() + "!", 5)
                    return

        # Weapon / Kunai attack (L)
        if ord("l") in keys or ord("L") in keys:
            if not f.on_ground:
                f.start_move("kunai_throw")
            elif crouch or f.weapon == WEAPON_FISTS:
                f.start_move("kunai_throw")
            elif f.weapon == WEAPON_KATANA:
                f.start_move("katana_heavy" if forward_held else "katana_slash")
            else:
                f.start_move("kusari_whip")
            return

        # Kick attack (K)
        if ord("k") in keys or ord("K") in keys:
            if not f.on_ground:
                f.start_move("air_kick")
            elif crouch:
                f.start_move("sweep")
            elif forward_held:
                f.start_move("roundhouse")
            else:
                f.start_move("high_kick")
            return

        # Punch attack (J)
        if ord("j") in keys or ord("J") in keys:
            if not f.on_ground:
                f.start_move("air_kick")
            elif crouch:
                f.start_move("uppercut")
            elif forward_held or (f.state == STATE_ATTACK and f.current_move and f.current_move.name == "Shadow Jab"):
                f.start_move("cross")
            else:
                f.start_move("jab")
            return

        # Dash (E)
        if dash_key and f.can_act and f.on_ground:
            dash_dir = -1 if move_left else (+1 if move_right else f.facing)
            if f.start_dash(dash_dir):
                self.spawn_hit_sparks(f.x, f.y - 1, 5, 4)
                return

        # Movement & Guarding when able to act
        if f.can_act:
            if jump and f.on_ground:
                f.vy = -3.1
                f.state = STATE_JUMP
                f.blocking = False
                if move_left:
                    f.vx = -1.4
                elif move_right:
                    f.vx = 1.4
                return

            if not f.on_ground:
                if move_left:
                    f.vx = max(f.vx - 0.3, -1.6)
                elif move_right:
                    f.vx = min(f.vx + 0.3, 1.6)
                return

            if crouch:
                f.state = STATE_CROUCH
                f.vx = 0.0
                f.blocking = True
                f.block_frames += 1
                return

            speed = 1.55 if f.shadow_form else 1.15
            if move_left:
                f.vx = -speed
                f.state = STATE_WALK
                f.walk_cycle += 1
                f.blocking = backward_held
                f.block_frames = f.block_frames + 1 if backward_held else 0
            elif move_right:
                f.vx = speed
                f.state = STATE_WALK
                f.walk_cycle += 1
                f.blocking = backward_held
                f.block_frames = f.block_frames + 1 if backward_held else 0
            else:
                f.vx = 0.0
                f.state = STATE_IDLE
                f.blocking = False
                f.block_frames = 0

    def process_ai(self, ai: Fighter, opponent: Fighter) -> None:
        """Tactical Shadow Fight AI controller with spacing, blocking, combos, and shadow moves."""
        if self.round_over:
            return

        dist = abs(opponent.x - ai.x)
        if ai.ai_cooldown > 0:
            ai.ai_cooldown -= 1

        # Activate Shadow Form when full
        if ai.shadow >= 95.0 and not ai.shadow_form and ai.can_act:
            if ai.activate_shadow_form():
                self.add_floating_text(ai.x, ai.y - 8, "SHADOW SURGE!", 5)
                self.spawn_hit_sparks(ai.x, ai.y - 3, 14, 5, heavy=True)
                return

        # Combo continuation if Jab connected
        if (
            ai.state == STATE_ATTACK
            and ai.current_move is not None
            and ai.current_move.name == "Shadow Jab"
            and ai.move_has_hit
            and random.random() < 0.75
        ):
            if ai.weapon == WEAPON_KUSARI:
                followup = random.choice(["cross", "high_kick", "kusari_whip"])
            elif ai.weapon == WEAPON_KATANA:
                followup = random.choice(["cross", "high_kick", "katana_slash"])
            else:
                followup = random.choice(["cross", "high_kick", "uppercut"])
            ai.start_move(followup)
            return

        if not ai.can_act:
            return

        # Airborne AI: execute air kick when near opponent; do not walk or crouch in mid-air
        if not ai.on_ground:
            if ai.state == STATE_JUMP and dist < 13.0 and random.random() < 0.35 * self.ai_difficulty:
                ai.start_move("air_kick")
            return

        # Defensive reaction when opponent is attacking within range
        opp_attacking = opponent.state == STATE_ATTACK and opponent.current_move is not None
        react_chance = 0.28 + 0.22 * self.ai_difficulty
        if opp_attacking and dist < 17 and random.random() < react_chance:
            ai.vx = 0.0
            if opponent.current_move.is_low:
                ai.state = STATE_CROUCH
            else:
                ai.state = STATE_IDLE
            ai.blocking = True
            ai.block_frames += 1
            return

        # Shadow Ability usage when energy >= 50
        if ai.shadow >= 50.0 and dist < 22 and ai.ai_cooldown == 0 and random.random() < 0.08 * self.ai_difficulty:
            ability = "shadow_eruption" if dist < 13 and random.random() < 0.5 else "shadow_strike"
            if ai.start_move(ability):
                if ability == "shadow_strike":
                    target_x = opponent.x - ai.facing * 9.0
                    ai.x = max(6.0, min(STAGE_WIDTH - 6.0, (ai.x + target_x) * 0.5))
                self.spawn_hit_sparks(ai.x, ai.y - 3, 12, 5, heavy=True)
                self.add_floating_text(ai.x, ai.y - 8, MOVES[ability].name.upper() + "!", 5)
                ai.ai_cooldown = 14
                return

        # Far range: close distance, dash, or throw kunai
        if dist > 18.0:
            ai.blocking = False
            ai.block_frames = 0
            if ai.ai_cooldown == 0 and random.random() < 0.04 * self.ai_difficulty:
                ai.start_move("kunai_throw")
                ai.ai_cooldown = 18
                return
            if dist > 26.0 and random.random() < 0.06:
                ai.start_dash(ai.facing)
                return
            speed = 1.45 if ai.shadow_form else 1.10
            ai.vx = ai.facing * speed
            ai.state = STATE_WALK
            ai.walk_cycle += 1
            return

        # Mid range (10..18): weapon strikes, roundhouse, jump-in, or step in
        if dist > 9.0:
            ai.blocking = False
            ai.block_frames = 0
            if ai.ai_cooldown == 0 and random.random() < 0.14 * self.ai_difficulty:
                if ai.weapon == WEAPON_KUSARI:
                    choice = random.choice(["kusari_whip", "roundhouse", "high_kick"])
                elif ai.weapon == WEAPON_KATANA:
                    choice = random.choice(["katana_slash", "katana_heavy", "roundhouse"])
                else:
                    choice = random.choice(["roundhouse", "high_kick", "kunai_throw"])
                ai.start_move(choice)
                ai.ai_cooldown = max(6, 15 - 3 * self.ai_difficulty)
                return
            if random.random() < 0.04 and ai.on_ground:
                ai.vy = -3.0
                ai.vx = ai.facing * 1.4
                ai.state = STATE_JUMP
                return
            speed = 1.3 if ai.shadow_form else 1.0
            ai.vx = ai.facing * speed
            ai.state = STATE_WALK
            ai.walk_cycle += 1
            return

        # Close range (<= 9): fast mixups (jab, sweep, uppercut, cross)
        if ai.ai_cooldown == 0 and random.random() < 0.24 * self.ai_difficulty:
            ai.blocking = False
            ai.block_frames = 0
            if opponent.blocking and opponent.state == STATE_CROUCH:
                choice = random.choice(["katana_heavy", "jab", "cross"])  # roundhouse is high: whiffs on crouch
            elif opponent.blocking:
                choice = random.choice(["sweep", "uppercut", "jab"])
            else:
                choice = random.choice(["jab", "cross", "sweep", "uppercut", "high_kick"])
            ai.start_move(choice)
            ai.ai_cooldown = max(5, 14 - 3 * self.ai_difficulty)
            return

        # Slight spacing adjustment or short guard
        if random.random() < 0.25:
            ai.vx = 0.0
            ai.state = STATE_IDLE
            ai.blocking = True
            ai.block_frames += 1
        else:
            ai.blocking = False
            ai.block_frames = 0
            ai.vx = 0.0
            ai.state = STATE_IDLE

    def update_fighter_physics(self, f: Fighter, opponent: Fighter) -> None:
        # Update facing when able to act on ground
        if f.on_ground and f.state in (STATE_IDLE, STATE_WALK, STATE_CROUCH):
            if opponent.x > f.x + 0.5:
                f.facing = +1
            elif opponent.x < f.x - 0.5:
                f.facing = -1

        # Shadow Form drain & aura particles
        if f.shadow_form:
            f.shadow = max(0.0, f.shadow - 0.45)
            if random.random() < 0.65:
                self.particles.append(
                    Particle(
                        x=f.x + random.uniform(-2.5, 2.5),
                        y=f.y - random.uniform(0.5, 5.5),
                        vx=random.uniform(-0.2, 0.2),
                        vy=-random.uniform(0.3, 0.8),
                        char=random.choice(["^", "*", "."]),
                        color_pair=5,
                        ttl=6,
                    )
                )
            if f.shadow <= 0.0:
                f.shadow_form = False

        # Combo timer decay
        if f.combo_timer > 0:
            f.combo_timer -= 1
            if f.combo_timer == 0:
                f.combo_count = 0

        # Horizontal & vertical integration
        f.x += f.vx
        f.y += f.vy

        if f.y < GROUND_Y or f.vy < 0:
            f.vy += GRAVITY
        if f.y >= GROUND_Y:
            was_airborne = f.vy > 0 or f.state == STATE_JUMP
            f.y = float(GROUND_Y)
            f.vy = 0.0
            if was_airborne and (
                f.state == STATE_JUMP
                or (f.state == STATE_ATTACK and f.current_move and f.current_move.name in ("Flying Shadow Kick", "Shadow Kunai"))
            ):
                f.state = STATE_IDLE
                f.current_move = None
                f.vx = 0.0

        # Ground friction during non-walk states
        if f.on_ground and f.state not in (STATE_WALK, STATE_DASH):
            f.vx *= 0.62
            if abs(f.vx) < 0.08:
                f.vx = 0.0

        # Keep within arena walls
        f.x = max(5.0, min(STAGE_WIDTH - 5.0, f.x))

        # Advance state timers
        if f.state == STATE_ATTACK and f.current_move is not None:
            m = f.current_move
            # Spawn projectile on the first active frame if applicable
            if m.spawns_projectile and f.move_frame == m.startup:
                self.projectiles.append(
                    Projectile(
                        owner_id=f.fighter_id,
                        x=f.x + f.facing * 3.0,
                        y=f.y - 3.5,
                        vx=f.facing * 2.8,
                        damage=m.damage * (SHADOW_FORM_DAMAGE_MULT if f.shadow_form else 1.0),
                        shadow_gain=m.shadow_gain,
                    )
                )
            f.move_frame += 1
            if f.move_frame >= m.total_frames:
                f.state = STATE_CROUCH if m.pose_recovery == "crouch" else (STATE_JUMP if not f.on_ground else STATE_IDLE)
                f.current_move = None
                f.move_frame = 0
                f.move_has_hit = False

        elif f.state in (STATE_DASH, STATE_HITSTUN, STATE_KNOCKDOWN):
            f.state_timer -= 1
            if f.state_timer <= 0:
                if f.hp <= 0:
                    f.state = STATE_DEFEAT
                else:
                    f.state = STATE_IDLE
                    f.vx = 0.0

    def resolve_pushbox(self) -> None:
        """Prevent fighters from overlapping horizontally."""
        min_sep = 4.2
        dx = self.p2.x - self.p1.x
        if abs(dx) < min_sep:
            overlap = (min_sep - abs(dx)) * 0.5
            sign = 1.0 if dx >= 0 else -1.0
            self.p1.x = max(5.0, min(STAGE_WIDTH - 5.0, self.p1.x - sign * overlap))
            self.p2.x = max(5.0, min(STAGE_WIDTH - 5.0, self.p2.x + sign * overlap))

    @staticmethod
    def boxes_overlap(b1: Tuple[float, float, float, float], b2: Tuple[float, float, float, float]) -> bool:
        return not (b1[2] < b2[0] or b1[0] > b2[2] or b1[3] < b2[1] or b1[1] > b2[3])

    def _latch_held_keys(self, keys: Set[int]) -> Set[int]:
        """Keep held-type keys (move/crouch/guard) alive across short terminal key-repeat gaps."""
        out = set(keys)
        pressed_left = bool(keys & LEFT_KEYS)
        pressed_right = bool(keys & RIGHT_KEYS)
        for k in list(self.hold_age):
            if k in keys:
                continue
            # A fresh press of the opposite direction must win immediately
            if (pressed_right and k in LEFT_KEYS) or (pressed_left and k in RIGHT_KEYS):
                del self.hold_age[k]
                continue
            self.hold_age[k] += 1
            if self.hold_age[k] <= HOLD_GRACE_FRAMES:
                out.add(k)
            else:
                del self.hold_age[k]
        for k in keys:
            if k in HOLD_KEYS:
                self.hold_age[k] = 0
        return out

    def _set_hitstop(self, frames: int) -> None:
        self.hitstop_frames = max(self.hitstop_frames, frames)

    def _set_shake(self, frames: int) -> None:
        self.screen_shake = max(self.screen_shake, frames)

    def _plan_hit(
        self,
        attacker: Fighter,
        defender: Fighter,
        *,
        damage: float,
        shadow_gain: float,
        knockback_x: float,
        knockback_y: float,
        hitstun: int,
        causes_knockdown: bool,
        is_low: bool,
        is_overhead: bool,
        push_dir: int,
        hit_x: float,
        hit_y: float,
        is_projectile: bool = False,
        shadowy: bool = False,
    ) -> HitPlan:
        """Decide parry / block / hit from the defender's CURRENT state, without changing anything."""
        guard_valid = defender.blocking
        if guard_valid:
            if is_low and defender.state != STATE_CROUCH:
                guard_valid = False
            elif is_overhead and defender.state == STATE_CROUCH:
                guard_valid = False

        if guard_valid and 1 <= defender.block_frames <= 3:
            kind = "parry"  # Just-frame parry: guard started within the last 3 frames
        elif guard_valid:
            kind = "block"
        else:
            kind = "hit"

        is_counter = (
            kind == "hit"
            and defender.state == STATE_ATTACK
            and defender.current_move is not None
            and defender.move_frame < defender.current_move.startup
        )
        return HitPlan(
            attacker=attacker, defender=defender, kind=kind, damage=damage, shadow_gain=shadow_gain,
            knockback_x=knockback_x, knockback_y=knockback_y, hitstun=hitstun,
            causes_knockdown=causes_knockdown, push_dir=push_dir, hit_x=hit_x, hit_y=hit_y,
            is_counter=is_counter, is_projectile=is_projectile, shadowy=shadowy,
        )

    def _plan_melee(self, attacker: Fighter, defender: Fighter) -> Optional[HitPlan]:
        if self.round_over or attacker.state != STATE_ATTACK or attacker.current_move is None or attacker.move_has_hit:
            return None
        hitbox = attacker.get_active_hitbox()
        if hitbox is None or defender.is_invulnerable():
            return None
        move = attacker.current_move
        if move.is_high and defender.state == STATE_CROUCH:
            return None  # High attacks sail over a crouching defender
        hurtbox = defender.get_hurtbox()
        if not self.boxes_overlap(hitbox, hurtbox):
            return None
        hit_x = (max(hitbox[0], hurtbox[0]) + min(hitbox[2], hurtbox[2])) * 0.5
        hit_y = (max(hitbox[1], hurtbox[1]) + min(hitbox[3], hurtbox[3])) * 0.5
        return self._plan_hit(
            attacker, defender,
            damage=move.damage, shadow_gain=move.shadow_gain,
            knockback_x=move.knockback_x, knockback_y=move.knockback_y, hitstun=move.hitstun,
            causes_knockdown=move.causes_knockdown, is_low=move.is_low, is_overhead=move.is_overhead,
            push_dir=attacker.facing, hit_x=hit_x, hit_y=hit_y, shadowy=move.shadow_cost > 0,
        )

    def _apply_hit(self, plan: HitPlan) -> None:
        a, d = plan.attacker, plan.defender
        if not plan.is_projectile:
            a.move_has_hit = True

        if plan.kind == "parry":
            d.shadow = min(d.max_shadow, d.shadow + 15.0)
            if not plan.is_projectile:  # A parried projectile is simply destroyed
                a.state = STATE_HITSTUN
                a.state_timer = 8
                a.current_move = None
                a.vx = -a.facing * 2.0
            self._set_hitstop(3)
            self.spawn_hit_sparks(plan.hit_x, plan.hit_y, 12, 4, heavy=True)
            self.add_floating_text(d.x, d.y - 7, "PARRY! +15 SHADOW", 4)
            return

        if plan.kind == "block":
            chip_dmg = max(1.0, plan.damage * 0.18)
            d.hp = max(0.0, d.hp - chip_dmg)
            d.vx = plan.push_dir * plan.knockback_x * 0.45
            if a.shadow_form:  # Same rule as an unblocked hit: lifesteal instead of shadow gain
                a.hp = min(a.max_hp, a.hp + chip_dmg * 0.25)
            else:
                a.shadow = min(a.max_shadow, a.shadow + plan.shadow_gain * 0.35)
            d.shadow = min(d.max_shadow, d.shadow + plan.shadow_gain * 0.25)
            self.spawn_hit_sparks(plan.hit_x, plan.hit_y, 6, 4, heavy=False)
            self.add_floating_text(d.x, d.y - 7, "DEFLECTED" if plan.is_projectile else "BLOCKED", 4)
            self._set_hitstop(1)
            return

        # Unblocked hit
        d.combo_count += 1
        d.combo_timer = 32
        combo_scale = max(0.45, 1.0 - 0.10 * (d.combo_count - 1))
        # Projectile damage already carries the Shadow Form multiplier from when it was spawned
        shadow_mult = SHADOW_FORM_DAMAGE_MULT if (a.shadow_form and not plan.is_projectile) else 1.0
        counter_mult = 1.25 if plan.is_counter else 1.0

        final_dmg = plan.damage * combo_scale * shadow_mult * counter_mult
        d.hp = max(0.0, d.hp - final_dmg)

        if a.shadow_form:
            a.hp = min(a.max_hp, a.hp + final_dmg * 0.25)
        else:
            a.shadow = min(a.max_shadow, a.shadow + plan.shadow_gain)
        d.shadow = min(d.max_shadow, d.shadow + plan.shadow_gain * 0.55)

        d.current_move = None
        d.blocking = False
        d.block_frames = 0
        d.vx = plan.push_dir * plan.knockback_x
        if plan.knockback_y < 0:
            d.vy = plan.knockback_y

        if plan.causes_knockdown or d.hp <= 0:
            d.state = STATE_KNOCKDOWN if d.hp > 0 else STATE_DEFEAT
            d.state_timer = 18
            self._set_shake(4)
            self._set_hitstop(3)
        else:
            d.state = STATE_HITSTUN
            d.state_timer = plan.hitstun + (3 if plan.is_counter else 0)
            if final_dmg >= 14:
                self._set_shake(2)
                self._set_hitstop(2)
            else:
                self._set_hitstop(1)

        spark_color = 5 if (plan.shadowy or a.shadow_form) else 3
        self.spawn_hit_sparks(plan.hit_x, plan.hit_y, 14 if final_dmg >= 14 else 8, spark_color, heavy=(final_dmg >= 14))

        label = f"KUNAI -{int(round(final_dmg))}" if plan.is_projectile else f"-{int(round(final_dmg))}"
        if plan.is_counter:
            label = f"COUNTER! {label}"
        elif d.combo_count >= 2:
            label = f"{d.combo_count}x HIT! {label}"
        self.add_floating_text(d.x, d.y - 7, label, spark_color)

    def check_melee_hits(self) -> None:
        """Resolve both fighters' melee contacts from the SAME snapshot so neither has priority."""
        plans = [self._plan_melee(self.p1, self.p2), self._plan_melee(self.p2, self.p1)]
        for plan in plans:
            if plan is not None:
                self._apply_hit(plan)

    def check_melee_hit(self, attacker: Fighter, defender: Fighter) -> None:
        """Single-direction resolve (kept for API compatibility)."""
        plan = self._plan_melee(attacker, defender)
        if plan is not None:
            self._apply_hit(plan)

    def update_projectiles(self) -> None:
        if self.round_over:
            self.projectiles.clear()
            return

        spec = MOVES["kunai_throw"]
        for proj in self.projectiles:
            if not proj.active:
                continue
            proj.x += proj.vx
            proj.ttl -= 1
            if proj.ttl <= 0 or proj.x < 2 or proj.x > STAGE_WIDTH - 2:
                proj.active = False
                continue

            target = self.p2 if proj.owner_id == 1 else self.p1
            attacker = self.p1 if proj.owner_id == 1 else self.p2
            if target.is_invulnerable():
                continue  # Same rule as melee: invulnerable targets are passed through

            hurtbox = target.get_hurtbox()
            pbox = (proj.x - 1.5, proj.y - 0.5, proj.x + 1.5, proj.y + 0.5)
            if self.boxes_overlap(pbox, hurtbox):
                proj.active = False
                plan = self._plan_hit(
                    attacker, target,
                    damage=proj.damage, shadow_gain=proj.shadow_gain,
                    knockback_x=spec.knockback_x, knockback_y=spec.knockback_y, hitstun=spec.hitstun,
                    causes_knockdown=False, is_low=False, is_overhead=False,
                    push_dir=1 if proj.vx > 0 else -1, hit_x=proj.x, hit_y=proj.y, is_projectile=True,
                )
                self._apply_hit(plan)

        self.projectiles = [p for p in self.projectiles if p.active]

    def update_fx(self) -> None:
        for pt in self.particles:
            pt.x += pt.vx
            pt.y += pt.vy
            pt.ttl -= 1
        self.particles = [pt for pt in self.particles if pt.ttl > 0]

        for ft in self.floating_texts:
            ft.y -= 0.18
            ft.ttl -= 1
        self.floating_texts = [ft for ft in self.floating_texts if ft.ttl > 0]

        if self.screen_shake > 0:
            self.screen_shake -= 1
        if self.announcer_timer > 0:
            self.announcer_timer -= 1

    def check_round_end(self) -> None:
        if self.round_over:
            self.round_over_timer -= 1
            if self.round_over_timer <= 0 and self.match_winner is None:
                self.start_next_round()
            return

        p1_ko = self.p1.hp <= 0
        p2_ko = self.p2.hp <= 0
        timeout = self.round_timer <= 0

        if p1_ko or p2_ko or timeout:
            self.round_over = True
            self.round_over_timer = 65
            if p1_ko and p2_ko:
                self.announcer_text = "DOUBLE K.O.!"
            elif p2_ko or (timeout and self.p1.hp > self.p2.hp):
                self.p1.rounds_won += 1
                self.p1.state = STATE_VICTORY
                self.p2.state = STATE_DEFEAT
                win_type = "K.O.!" if p2_ko else "TIME OVER!"
                self.announcer_text = f"{win_type} {self.p1.name} WINS ROUND {self.round_num}!"
            elif p1_ko or (timeout and self.p2.hp > self.p1.hp):
                self.p2.rounds_won += 1
                self.p2.state = STATE_VICTORY
                self.p1.state = STATE_DEFEAT
                win_type = "K.O.!" if p1_ko else "TIME OVER!"
                self.announcer_text = f"{win_type} {self.p2.name} WINS ROUND {self.round_num}!"
            else:
                self.announcer_text = "TIME OVER - DRAW!"

            self.announcer_timer = 65
            if self.p1.rounds_won >= 2:
                self.match_winner = self.p1
                self.announcer_text = f"CHAMPION: {self.p1.name}! (PRESS R TO REMATCH, Q TO QUIT)"
            elif self.p2.rounds_won >= 2:
                self.match_winner = self.p2
                self.announcer_text = f"VICTOR: {self.p2.name}! (PRESS R TO REMATCH, Q TO QUIT)"

    def step(self, keys: Set[int]) -> None:
        """Advance the game simulation by one tick."""
        if self.paused:
            return

        # Hitstop freeze frames for impactful heavy hits
        if self.hitstop_frames > 0:
            self.hitstop_frames -= 1
            self.buffered_keys |= keys  # Do not lose presses made while frozen
            self.update_fx()
            return

        if self.buffered_keys:
            keys = keys | self.buffered_keys
            self.buffered_keys = set()

        if not self.round_over:
            self.round_timer = max(0, self.round_timer - 1)

        if self.p1.is_ai:
            self.process_ai(self.p1, self.p2)
        else:
            self.process_player_input(self.p1, self.p2, self._latch_held_keys(keys))

        if self.p2.is_ai:
            self.process_ai(self.p2, self.p1)

        self.update_fighter_physics(self.p1, self.p2)
        self.update_fighter_physics(self.p2, self.p1)
        self.resolve_pushbox()

        self.check_melee_hits()
        self.update_projectiles()
        self.update_fx()
        self.check_round_end()


# ---------------------------------------------------------------------------
# Universal Virtual Canvas & Scene Compositor (Shared by ANSI & Curses)
# ---------------------------------------------------------------------------
class VirtualCanvas:
    """2D character + style buffer that renders either via ANSI escapes or curses."""

    def __init__(self, width: int, height: int):
        self.width = max(20, width)
        self.height = max(10, height)
        self.chars: List[List[str]] = [[" "] * self.width for _ in range(self.height)]
        # Each cell stores (pair_id, bold, dim)
        self.styles: List[List[Tuple[int, bool, bool]]] = [
            [(7, False, False)] * self.width for _ in range(self.height)
        ]

    def clear(self, width: int, height: int) -> None:
        self.width = max(20, width)
        self.height = max(10, height)
        self.chars = [[" "] * self.width for _ in range(self.height)]
        self.styles = [[(7, False, False)] * self.width for _ in range(self.height)]

    def put_str(
        self, y: int, x: int, text: str, pair_id: int = 7, bold: bool = False, dim: bool = False
    ) -> None:
        if y < 0 or y >= self.height or x >= self.width or not text:
            return
        if x < 0:
            text = text[-x:]
            x = 0
        limit = min(len(text), self.width - x)
        if limit <= 0:
            return
        row_c = self.chars[y]
        row_s = self.styles[y]
        style = (pair_id, bold, dim)
        for i in range(limit):
            row_c[x + i] = text[i]
            row_s[x + i] = style

    def draw_bar(
        self, y: int, x: int, width: int, ratio: float, fill_pair: int, reverse: bool = False
    ) -> None:
        ratio = max(0.0, min(1.0, ratio))
        filled = int(round(width * ratio))
        empty = width - filled
        if reverse:
            self.put_str(y, x, "[", 7, bold=True)
            self.put_str(y, x + 1, "." * empty, 7, dim=True)
            self.put_str(y, x + 1 + empty, "#" * filled, fill_pair, bold=True)
            self.put_str(y, x + 1 + width, "]", 7, bold=True)
        else:
            self.put_str(y, x, "[", 7, bold=True)
            self.put_str(y, x + 1, "#" * filled, fill_pair, bold=True)
            self.put_str(y, x + 1 + filled, "." * empty, 7, dim=True)
            self.put_str(y, x + 1 + width, "]", 7, bold=True)


def compose_title_scene(canvas: VirtualCanvas, selected_diff: int) -> None:
    ox = max(0, (canvas.width - 84) // 2)
    oy = max(0, (canvas.height - 22) // 2)

    banner = [
        " ____  _   _    _    ____   _____ _      _____ ___ ____ _   _ _____ ",
        "/ ___|| | | |  / \\  |  _ \\ / _ \\ \\      / /  _|_ _/ ___| | | |_   _|",
        "\\___ \\| |_| | / _ \\ | | | | | | \\ \\ /\\ / /| |_ | | |  _| |_| | | |  ",
        " ___) |  _  |/ ___ \\| |_| | |_| |\\ V  V / |  _|| | |_| |  _  | | |  ",
        "|____/|_| |_/_/   \\_\\____/ \\___/  \\_/\\_/  |_| |___\\____|_| |_| |_|  ",
        "               E C L I P S E   S T I C K M A N   D U E L            ",
    ]
    for idx, line in enumerate(banner):
        canvas.put_str(oy + idx, ox + 6, line, 5, bold=True)

    duel_art = [
        "             (_)                                   (_)             ",
        "            / |====/             VS           \\====| \\            ",
        "           /  |   /                             \\   |  \\           ",
        "             / \\                                   / \\             ",
    ]
    for idx, line in enumerate(duel_art):
        canvas.put_str(oy + 7 + idx, ox + 6, line, 3, bold=True)

    diff_names = {1: "1: INITIATE (Easy)", 2: "2: RONIN (Medium)", 3: "3: SHADOW MASTER (Hard)"}
    canvas.put_str(oy + 12, ox + 16, "Select AI Difficulty (Press 1 / 2 / 3):", 7, bold=True)
    for d in (1, 2, 3):
        prefix = ">> " if d == selected_diff else "   "
        pair = 3 if d == selected_diff else 7
        canvas.put_str(oy + 13 + d, ox + 22, f"{prefix}{diff_names[d]}", pair, bold=(d == selected_diff))

    canvas.put_str(oy + 18, ox + 14, "Press [ENTER] or [SPACE] to Start 1P vs AI Duel", 6, bold=True)
    canvas.put_str(oy + 19, ox + 14, "Press [V] to Watch AI vs AI Exhibition Match", 1, bold=True)
    canvas.put_str(oy + 20, ox + 14, "Press [Q] to Exit", 2, bold=True)


def compose_battle_scene(canvas: VirtualCanvas, engine: ShadowFightEngine) -> None:
    ox = max(0, (canvas.width - STAGE_WIDTH) // 2)
    oy = max(0, (canvas.height - STAGE_HEIGHT) // 2)
    if engine.screen_shake > 0:
        ox = max(0, ox + random.choice([-1, 1]))

    # 1. Backdrop (Stars, Moon, Pagoda, Torii Pillars, Tatami Floor)
    for sx, sy in engine.stars:
        canvas.put_str(oy + sy, ox + sx, ".", 7, dim=True)

    moon = [
        "   _..._   ",
        " .:::::::. ",
        ":::::::::::",
        ":::::::::::",
        " `:::::::' ",
    ]
    for idx, line in enumerate(moon):
        canvas.put_str(oy + 5 + idx, ox + 44, line, 3, bold=True)

    pagoda = [
        "        /^\\        ",
        "    ___/   \\___    ",
        "   /===========\\   ",
        "     |  _ _  |     ",
        "  ___/  | |  \\___  ",
        " /===============\\ ",
        "   |  |     |  |   ",
    ]
    for idx, line in enumerate(pagoda):
        canvas.put_str(oy + 11 + idx, ox + 40, line, 7, dim=True)

    for row in range(12, GROUND_Y):
        canvas.put_str(oy + row, ox + 8, "||", 2, dim=True)
        canvas.put_str(oy + row, ox + STAGE_WIDTH - 10, "||", 2, dim=True)
    canvas.put_str(oy + 11, ox + 5, "==/==\\==", 2, bold=True)
    canvas.put_str(oy + 11, ox + STAGE_WIDTH - 13, "==/==\\==", 2, bold=True)

    canvas.put_str(oy + GROUND_Y, ox, "=" * STAGE_WIDTH, 7, bold=True)
    canvas.put_str(oy + GROUND_Y + 1, ox, "/\\  " * (STAGE_WIDTH // 4), 7, dim=True)

    # 2. HUD Top Bar
    p1, p2 = engine.p1, engine.p2
    p1_rounds = ("(*) " * p1.rounds_won) + ("( ) " * max(0, 2 - p1.rounds_won))
    p2_rounds = ("( ) " * max(0, 2 - p2.rounds_won)) + ("(*) " * p2.rounds_won)

    canvas.put_str(oy + 0, ox + 2, f"{p1.name} [{p1.weapon}]", 1, bold=True)
    canvas.put_str(oy + 0, ox + 36, p1_rounds, 3, bold=True)

    timer_sec = max(0, engine.round_timer // FPS)
    canvas.put_str(oy + 0, ox + 46, f"[{timer_sec:02d}]", 3, bold=True)

    canvas.put_str(oy + 0, ox + 55, p2_rounds, 3, bold=True)
    p2_header = f"[{p2.weapon}] {p2.name}"
    canvas.put_str(oy + 0, ox + STAGE_WIDTH - 2 - len(p2_header), p2_header, 2, bold=True)

    p1_hp_color = 6 if p1.hp > 30 else 2
    p2_hp_color = 6 if p2.hp > 30 else 2
    canvas.draw_bar(oy + 1, ox + 2, 38, p1.hp / p1.max_hp, p1_hp_color, reverse=False)
    canvas.draw_bar(oy + 1, ox + STAGE_WIDTH - 42, 38, p2.hp / p2.max_hp, p2_hp_color, reverse=True)
    canvas.put_str(oy + 1, ox + 44, f"{int(p1.hp):3d}|HP|{int(p2.hp):3d}", 7, bold=True)

    canvas.draw_bar(oy + 2, ox + 2, 30, p1.shadow / p1.max_shadow, 5, reverse=False)
    canvas.put_str(oy + 2, ox + 35, f"SHDW {int(p1.shadow):3d}%", 5, bold=True)

    canvas.put_str(oy + 2, ox + STAGE_WIDTH - 44, f"{int(p2.shadow):3d}% SHDW", 5, bold=True)
    canvas.draw_bar(oy + 2, ox + STAGE_WIDTH - 34, 30, p2.shadow / p2.max_shadow, 5, reverse=True)

    if p1.last_move_name:
        canvas.put_str(oy + 3, ox + 2, f"Move: {p1.last_move_name}", 1)
    if p2.last_move_name:
        txt = f"Move: {p2.last_move_name}"
        canvas.put_str(oy + 3, ox + STAGE_WIDTH - 2 - len(txt), txt, 2)

    # 3. Fighters
    for f, default_pair in ((p1, 1), (p2, 2)):
        pose = f.get_current_pose()
        lines = get_pose_lines(pose, f.facing)
        top_y = int(round(f.y)) - len(lines)
        left_x = int(round(f.x)) - 5
        pair = 5 if f.shadow_form else (3 if f.state == STATE_HITSTUN else default_pair)
        for row_idx, line in enumerate(lines):
            for col_idx, ch in enumerate(line):
                if ch != " ":
                    canvas.put_str(oy + top_y + row_idx, ox + left_x + col_idx, ch, pair, bold=True)
        shadow_str = "(===)" if f.on_ground else " (.) "
        canvas.put_str(oy + GROUND_Y, ox + int(round(f.x)) - 2, shadow_str, 7, dim=True)

    # 4. Projectiles
    for proj in engine.projectiles:
        glyph = "->>" if proj.vx > 0 else "<<-"
        canvas.put_str(oy + int(round(proj.y)), ox + int(round(proj.x)) - 1, glyph, 3, bold=True)

    # 5. Particles & Floating Combat Text
    for pt in engine.particles:
        canvas.put_str(oy + int(round(pt.y)), ox + int(round(pt.x)), pt.char, pt.color_pair, bold=True)

    for ft in engine.floating_texts:
        canvas.put_str(
            oy + int(round(ft.y)),
            ox + int(round(ft.x)) - len(ft.text) // 2,
            ft.text,
            ft.color_pair,
            bold=True,
        )

    # 6. Announcer Banner
    if engine.announcer_timer > 0 or engine.match_winner is not None:
        banner = f"=== {engine.announcer_text} ==="
        bx = ox + (STAGE_WIDTH - len(banner)) // 2
        canvas.put_str(oy + 6, bx, banner, 3, bold=True)

    # 7. Controls Footer
    controls_1 = "MOVE: A/D or Left/Right | JUMP: W/Up | CROUCH/BLOCK: S/Down | DASH: E | PAUSE: P | QUIT: Q"
    controls_2 = "PUNCH: J | KICK: K | WEAPON/KUNAI: L | SHADOW ABILITY (50%): U | SHADOW FORM: I | WEAPON: 1/2/3"
    canvas.put_str(oy + GROUND_Y + 2, ox + (STAGE_WIDTH - len(controls_1)) // 2, controls_1, 7)
    canvas.put_str(oy + GROUND_Y + 3, ox + (STAGE_WIDTH - len(controls_2)) // 2, controls_2, 5, bold=True)

    # 8. Pause Overlay
    if engine.paused:
        box_lines = [
            "+---------------- PAUSED / MOVE LIST ----------------+",
            "| J (Neutral/Fwd/Down) : Jab / Cross / Uppercut      |",
            "| K (Neutral/Fwd/Down) : High Kick / Roundhouse/Sweep|",
            "| L (Stand / Crouch)   : Weapon Attack / Kunai Throw |",
            "| U (Stand / Crouch)   : Void Blink / Abyss Eruption |",
            "| I (At >=50% Shadow)  : Unleash Shadow Form         |",
            "| 1 / 2 / 3            : Barehanded / Katana / Kusari|",
            "| S or Hold Back       : Guard (Just-Frame = PARRY!) |",
            "|          Press P to Resume or Q to Quit            |",
            "+----------------------------------------------------+",
        ]
        for idx, bline in enumerate(box_lines):
            canvas.put_str(oy + 7 + idx, ox + (STAGE_WIDTH - len(bline)) // 2, bline, 3, bold=True)


# ---------------------------------------------------------------------------
# Backend 1: Native Cross-Platform ANSI + msvcrt / termios (Works on Windows!)
# ---------------------------------------------------------------------------
ANSI_COLOR_MAP = {
    1: "36",  # Cyan
    2: "31",  # Red
    3: "33",  # Yellow
    4: "34",  # Blue
    5: "35",  # Magenta
    6: "32",  # Green
    7: "37",  # White
}


def enable_windows_ansi() -> None:
    """Enable VT100 ANSI escape sequence processing on Windows 10/11 PowerShell & CMD."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE = -11
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def read_windows_keys() -> Set[int]:
    """Non-blocking keyboard poll on Windows using standard-library `msvcrt`."""
    keys: Set[int] = set()
    if msvcrt is None:
        return keys
    while msvcrt.kbhit():
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ext = msvcrt.getch()
            if ext == b"K":
                keys.add(KEY_LEFT)
            elif ext == b"M":
                keys.add(KEY_RIGHT)
            elif ext == b"H":
                keys.add(KEY_UP)
            elif ext == b"P":
                keys.add(KEY_DOWN)
        elif ch:
            keys.add(ch[0])
    return keys


def read_posix_keys() -> Set[int]:
    """Non-blocking keyboard poll on POSIX (Linux/macOS) for ANSI mode."""
    keys: Set[int] = set()
    if select is None:
        return keys
    try:
        while select.select([sys.stdin], [], [], 0)[0]:
            ch = sys.stdin.read(1)
            if not ch:
                break
            if ch == "\x1b":
                # Check for ANSI escape sequences (arrow keys)
                if select.select([sys.stdin], [], [], 0.02)[0]:
                    seq = sys.stdin.read(2)
                    if seq == "[A":
                        keys.add(KEY_UP)
                    elif seq == "[B":
                        keys.add(KEY_DOWN)
                    elif seq == "[C":
                        keys.add(KEY_RIGHT)
                    elif seq == "[D":
                        keys.add(KEY_LEFT)
            else:
                keys.add(ord(ch))
    except Exception:
        pass
    return keys


def render_canvas_to_ansi(canvas: VirtualCanvas) -> str:
    """Serialize VirtualCanvas into a flicker-free ANSI frame string."""
    out: List[str] = ["\x1b[H"]  # Move cursor to top-left (home) without full screen flash
    for y in range(canvas.height):
        row_c = canvas.chars[y]
        row_s = canvas.styles[y]
        cur_style: Optional[Tuple[int, bool, bool]] = None
        line_parts: List[str] = []
        for x in range(canvas.width):
            st = row_s[x]
            if st != cur_style:
                pair_id, bold, dim = st
                sgr = ["0"]
                if bold:
                    sgr.append("1")
                elif dim:
                    sgr.append("2")
                sgr.append(ANSI_COLOR_MAP.get(pair_id, "37"))
                line_parts.append(f"\x1b[{';'.join(sgr)}m")
                cur_style = st
            line_parts.append(row_c[x])
        line_parts.append("\x1b[0m\x1b[K")
        out.append("".join(line_parts))
    return "\n".join(out)


def run_ansi_app(demo_mode: bool = False, max_demo_frames: int = 0) -> None:
    """Run the interactive loop using native ANSI terminal output (ideal for Windows)."""
    enable_windows_ansi()
    difficulty = 2
    in_title = not demo_mode
    engine = ShadowFightEngine(ai_difficulty=difficulty, p1_is_ai=demo_mode)
    canvas = VirtualCanvas(STAGE_WIDTH, STAGE_HEIGHT)

    # Enter alternate screen buffer and hide cursor
    sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
    sys.stdout.flush()
    try:
        frames_run = 0
        while True:
            t0 = time.monotonic()
            term_size = shutil.get_terminal_size((104, 28))
            w = max(80, term_size.columns - 1)
            h = max(24, term_size.lines - 1)
            canvas.clear(w, h)

            keys = read_windows_keys() if os.name == "nt" else read_posix_keys()
            if 3 in keys:  # Ctrl+C interrupt
                return

            if in_title:
                if ord("q") in keys or ord("Q") in keys:
                    return
                if ord("1") in keys:
                    difficulty = 1
                elif ord("2") in keys:
                    difficulty = 2
                elif ord("3") in keys:
                    difficulty = 3
                if ord("\n") in keys or ord("\r") in keys or ord(" ") in keys:
                    engine = ShadowFightEngine(ai_difficulty=difficulty, p1_is_ai=False)
                    in_title = False
                    continue
                if ord("v") in keys or ord("V") in keys:
                    engine = ShadowFightEngine(ai_difficulty=difficulty, p1_is_ai=True)
                    in_title = False
                    continue
                compose_title_scene(canvas, difficulty)
            else:
                if ord("q") in keys or ord("Q") in keys:
                    if demo_mode:
                        return
                    in_title = True
                    continue
                if ord("p") in keys or ord("P") in keys:
                    engine.paused = not engine.paused
                if (ord("r") in keys or ord("R") in keys) and engine.match_winner is not None:
                    engine.reset_match(p1_is_ai=engine.p1.is_ai)

                engine.step(keys)
                compose_battle_scene(canvas, engine)
                frames_run += 1
                if max_demo_frames > 0 and frames_run >= max_demo_frames:
                    return

            sys.stdout.write(render_canvas_to_ansi(canvas))
            sys.stdout.flush()

            elapsed = time.monotonic() - t0
            sleep_time = FRAME_TIME - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    finally:
        # Restore cursor and main screen buffer
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l\n")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Backend 2: Curses Renderer (Linux / macOS or Windows with windows-curses)
# ---------------------------------------------------------------------------
class CursesRenderer:
    def __init__(self, stdscr: "_curses_mod._CursesWindow"):
        self.stdscr = stdscr
        _curses_mod.curs_set(0)
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)
        self.has_colors = _curses_mod.has_colors()
        if self.has_colors:
            _curses_mod.start_color()
            _curses_mod.use_default_colors()
            _curses_mod.init_pair(1, _curses_mod.COLOR_CYAN, -1)
            _curses_mod.init_pair(2, _curses_mod.COLOR_RED, -1)
            _curses_mod.init_pair(3, _curses_mod.COLOR_YELLOW, -1)
            _curses_mod.init_pair(4, _curses_mod.COLOR_BLUE, -1)
            _curses_mod.init_pair(5, _curses_mod.COLOR_MAGENTA, -1)
            _curses_mod.init_pair(6, _curses_mod.COLOR_GREEN, -1)
            _curses_mod.init_pair(7, _curses_mod.COLOR_WHITE, -1)

    def cpair(self, pair_id: int, bold: bool = False, dim: bool = False) -> int:
        attr = _curses_mod.color_pair(pair_id) if self.has_colors else 0
        if bold:
            attr |= _curses_mod.A_BOLD
        if dim:
            attr |= _curses_mod.A_DIM
        return attr

    def flush_canvas(self, canvas: VirtualCanvas) -> None:
        self.stdscr.erase()
        max_y, max_x = self.stdscr.getmaxyx()
        rows = min(canvas.height, max_y)
        cols = min(canvas.width, max_x - 1)
        for y in range(rows):
            row_c = canvas.chars[y]
            row_s = canvas.styles[y]
            x = 0
            while x < cols:
                if row_c[x] == " ":
                    x += 1
                    continue
                st = row_s[x]
                start_x = x
                buf = []
                while x < cols and row_s[x] == st:
                    if row_c[x] == " ":
                        # Include single internal spaces if next char has same style
                        if x + 1 < cols and row_c[x + 1] != " " and row_s[x + 1] == st:
                            buf.append(" ")
                            x += 1
                            continue
                        break
                    buf.append(row_c[x])
                    x += 1
                try:
                    self.stdscr.addstr(y, start_x, "".join(buf), self.cpair(*st))
                except _curses_mod.error:
                    pass
        self.stdscr.refresh()


def run_curses_app(stdscr: "_curses_mod._CursesWindow", demo_mode: bool = False, max_demo_frames: int = 0) -> None:
    renderer = CursesRenderer(stdscr)
    difficulty = 2
    in_title = not demo_mode
    engine = ShadowFightEngine(ai_difficulty=difficulty, p1_is_ai=demo_mode)
    canvas = VirtualCanvas(STAGE_WIDTH, STAGE_HEIGHT)

    frames_run = 0
    while True:
        t0 = time.monotonic()
        max_y, max_x = stdscr.getmaxyx()
        canvas.clear(max_x, max_y)

        keys: Set[int] = set()
        while True:
            ch = stdscr.getch()
            if ch == -1:
                break
            keys.add(ch)

        if in_title:
            if ord("q") in keys or ord("Q") in keys:
                return
            if ord("1") in keys:
                difficulty = 1
            elif ord("2") in keys:
                difficulty = 2
            elif ord("3") in keys:
                difficulty = 3
            if ord("\n") in keys or ord("\r") in keys or ord(" ") in keys:
                engine = ShadowFightEngine(ai_difficulty=difficulty, p1_is_ai=False)
                in_title = False
                continue
            if ord("v") in keys or ord("V") in keys:
                engine = ShadowFightEngine(ai_difficulty=difficulty, p1_is_ai=True)
                in_title = False
                continue
            compose_title_scene(canvas, difficulty)
            renderer.flush_canvas(canvas)
        else:
            if ord("q") in keys or ord("Q") in keys:
                if demo_mode:
                    return
                in_title = True
                continue
            if ord("p") in keys or ord("P") in keys:
                engine.paused = not engine.paused
            if (ord("r") in keys or ord("R") in keys) and engine.match_winner is not None:
                engine.reset_match(p1_is_ai=engine.p1.is_ai)

            engine.step(keys)
            compose_battle_scene(canvas, engine)
            renderer.flush_canvas(canvas)
            frames_run += 1
            if max_demo_frames > 0 and frames_run >= max_demo_frames:
                return

        elapsed = time.monotonic() - t0
        sleep_time = FRAME_TIME - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Built-in Self-Diagnostic Test Suite
# ---------------------------------------------------------------------------
def run_self_tests() -> int:
    print("Running Shadow Stickman Self-Diagnostic Test Suite...")
    random.seed(2024)  # Deterministic AI/particles for the test run

    # 1. Verify all poses have consistent 6-line height and clean mirroring
    for pose_name in POSE_ART_RIGHT:
        right_lines = get_pose_lines(pose_name, +1)
        left_lines = get_pose_lines(pose_name, -1)
        assert len(right_lines) == 6 and len(left_lines) == 6, f"Pose {pose_name} height mismatch"
        for rline, lline in zip(right_lines, left_lines):
            assert len(rline) == len(lline) == 11, f"Pose {pose_name} width mismatch: {len(rline)}"

    # 2. Verify every move executes through startup -> active -> recovery -> idle
    for move_key, spec in MOVES.items():
        eng = ShadowFightEngine()
        eng.p2.is_ai = False
        eng.p1.shadow = 100.0
        if move_key == "air_kick":
            eng.p1.y = GROUND_Y - 4.0
            eng.p1.state = STATE_JUMP
        started = eng.p1.start_move(move_key)
        assert started, f"Move {move_key} failed to start"
        active_seen = False
        for _ in range(spec.total_frames + 2):
            if eng.p1.get_active_hitbox() is not None or spec.spawns_projectile:
                active_seen = True
            eng.step(set())
        assert active_seen, f"Move {move_key} never produced active hitbox/projectile"
        assert eng.p1.state in (STATE_IDLE, STATE_CROUCH, STATE_JUMP), f"Move {move_key} stuck in {eng.p1.state}"

    # 3. Verify melee hit detection, guard reduction, parry, and shadow form
    eng = ShadowFightEngine()
    eng.p2.is_ai = False
    eng.p1.x = 45.0
    eng.p2.x = 50.0
    initial_hp = eng.p2.hp
    eng.step({ord("j")})
    for _ in range(10):
        eng.step(set())
    assert eng.p2.hp < initial_hp, "Unblocked jab should deal damage"

    # Guard test
    hp_before_block = eng.p2.hp
    eng.p2.blocking = True
    eng.p2.block_frames = 10  # Standard block (not parry)
    eng.p1.start_move("cross")
    for _ in range(15):
        eng.p2.blocking = True
        eng.p2.block_frames = 10
        eng.step(set())
    chip_taken = hp_before_block - eng.p2.hp
    assert 0 < chip_taken < MOVES["cross"].damage * 0.5, f"Block should reduce damage to chip (got {chip_taken})"

    # Parry test (block_frames in 1..3)
    eng.p2.state = STATE_IDLE
    eng.p2.blocking = True
    eng.p2.block_frames = 1
    hp_before_parry = eng.p2.hp
    eng.p1.start_move("jab")
    for _ in range(5):
        eng.p2.blocking = True
        eng.p2.block_frames = 2
        eng.step(set())
    assert eng.p2.hp == hp_before_parry, "Just-frame parry should negate all damage"
    assert eng.p1.state == STATE_HITSTUN, "Attacker should be put in hitstun on parry"

    # 4. Verify VirtualCanvas & ANSI renderer (Windows-compatible rendering path)
    canvas = VirtualCanvas(100, 26)
    compose_title_scene(canvas, 2)
    title_ansi = render_canvas_to_ansi(canvas)
    assert "E C L I P S E" in title_ansi, "Title banner missing from ANSI output"

    canvas.clear(100, 26)
    compose_battle_scene(canvas, eng)
    battle_ansi = render_canvas_to_ansi(canvas)
    assert "SHADOW RONIN" in battle_ansi and "ECLIPSE SHOGUN" in battle_ansi, "HUD missing from ANSI output"

    # 5. Simulate a full AI vs AI match until a winner is crowned
    sim = ShadowFightEngine(ai_difficulty=3, p1_is_ai=True)
    for _ in range(3000):
        sim.step(set())
        if sim.match_winner is not None:
            break
    assert sim.p1.rounds_won > 0 or sim.p2.rounds_won > 0, "AI vs AI simulation did not complete a round"

    # 6. Verify projectile hit cleanup and kusari combo cancel
    eng = ShadowFightEngine()
    eng.p2.is_ai = False
    eng.p2.blocking = True
    eng.p2.block_frames = 5
    eng.p2.current_move = MOVES["cross"]
    eng.p2.state = STATE_ATTACK
    eng.p2.blocking = False
    eng.projectiles.append(
        Projectile(owner_id=1, x=eng.p2.x, y=eng.p2.y - 3.5, vx=2.8, damage=8.0, shadow_gain=10.0)
    )
    eng.update_projectiles()
    assert eng.p2.current_move is None, "Projectile hit should reset defender current_move"
    assert eng.p2.blocking is False and eng.p2.block_frames == 0, "Projectile hit should reset guard state"

    # 7. Constructing an engine must not reseed the global RNG
    random.seed(123)
    expected_roll = random.random()
    random.seed(123)
    ShadowFightEngine()
    assert random.random() == expected_roll, "Engine construction must not touch the global RNG"
    random.seed(2024)

    # 8. Simultaneous hits are a true trade (no player-1 priority)
    eng = ShadowFightEngine()
    eng.p2.is_ai = False
    eng.p1.x, eng.p2.x = 45.0, 51.0
    eng.p1.start_move("cross")
    eng.p2.start_move("cross")
    for _ in range(14):
        eng.step(set())
    assert eng.p1.hp == eng.p2.hp < 100.0, f"Trade should hurt both equally (p1={eng.p1.hp}, p2={eng.p2.hp})"

    # 9. Presses made during hitstop are replayed afterwards
    eng = ShadowFightEngine()
    eng.p2.is_ai = False
    eng.hitstop_frames = 2
    eng.step({ord("j")})
    eng.step(set())
    eng.step(set())
    assert eng.p1.state == STATE_ATTACK, "Jab pressed during hitstop should execute once it ends"

    # 10. Crouching evades high attacks but not mid attacks
    for key, should_hit in (("high_kick", False), ("roundhouse", False), ("jab", True)):
        eng = ShadowFightEngine()
        eng.p2.is_ai = False
        eng.p1.x, eng.p2.x = 45.0, 50.0
        eng.p2.state = STATE_CROUCH
        eng.p1.start_move(key)
        for _ in range(16):
            eng.step(set())
        assert (eng.p2.hp < 100.0) == should_hit, f"{key} vs crouching defender: expected hit={should_hit}"

    # 11. Projectiles follow the same rules as melee (combo count, hitstop, parry)
    eng = ShadowFightEngine()
    eng.p2.is_ai = False
    eng.projectiles.append(Projectile(owner_id=1, x=eng.p2.x - 1, y=eng.p2.y - 3.5, vx=2.8, damage=8.0, shadow_gain=10.0))
    eng.update_projectiles()
    assert eng.p2.combo_count == 1 and eng.hitstop_frames >= 1, "Kunai hit should count as a combo hit and cause hitstop"
    eng = ShadowFightEngine()
    eng.p2.is_ai = False
    eng.p2.blocking = True
    eng.p2.block_frames = 2
    hp_before = eng.p2.hp
    eng.projectiles.append(Projectile(owner_id=1, x=eng.p2.x - 1, y=eng.p2.y - 3.5, vx=2.8, damage=8.0, shadow_gain=10.0))
    eng.update_projectiles()
    assert eng.p2.hp == hp_before and not eng.projectiles, "Just-frame parry should destroy a kunai without damage"
    assert eng.p1.state != STATE_HITSTUN, "Parrying a kunai must not stun the thrower"

    # 12. Shadow Form: guarded hits lifesteal like normal hits
    eng = ShadowFightEngine()
    eng.p2.is_ai = False
    eng.p1.shadow_form = True
    eng.p1.shadow = 60.0
    eng.p1.hp = 50.0
    eng.p1.x, eng.p2.x = 45.0, 50.0
    eng.p1.start_move("cross")
    for _ in range(12):
        eng.p2.blocking = True
        eng.p2.block_frames = 10
        eng.step(set())
    assert eng.p1.hp > 50.0, "Shadow Form lifesteal should also apply to guarded hits"

    # 13. Dash gives exactly 3 invulnerable frames
    eng = ShadowFightEngine()
    eng.p2.is_ai = False
    assert eng.p1.start_dash(+1)
    invulnerable_frames = 0
    for _ in range(8):
        eng.step(set())
        invulnerable_frames += 1 if eng.p1.is_invulnerable() else 0
    assert invulnerable_frames == 3, f"Dash should be invulnerable for 3 frames (got {invulnerable_frames})"

    # 14. A held guard survives a one-frame key-repeat gap, and direction changes are instant
    eng = ShadowFightEngine()
    eng.p2.is_ai = False
    for _ in range(10):
        eng.step({ord("s")})
    eng.step(set())
    eng.step({ord("s")})
    assert eng.p1.block_frames == 12, f"Guard should not flicker (block_frames={eng.p1.block_frames})"
    for _ in range(HOLD_GRACE_FRAMES + 1):
        eng.step(set())
    assert eng.p1.state == STATE_IDLE and eng.p1.block_frames == 0, "Guard should release after the grace window"
    eng = ShadowFightEngine()
    eng.p2.is_ai = False
    eng.step({ord("a")})
    eng.step({ord("d")})
    assert eng.p1.vx > 0, "Pressing the opposite direction must override a latched key immediately"

    print("All self-diagnostic checks passed with zero errors!")
    return 0


def main() -> int:
    if "--test" in sys.argv:
        return run_self_tests()
    demo_mode = "--demo" in sys.argv
    force_ansi = "--ansi" in sys.argv
    max_frames = 0
    for arg in sys.argv[1:]:
        if arg.startswith("--frames="):
            max_frames = int(arg.split("=", 1)[1])
        if arg.startswith("--seed="):
            random.seed(int(arg.split("=", 1)[1]))
    try:
        if HAS_CURSES and not force_ansi and os.name != "nt":
            _curses_mod.wrapper(run_curses_app, demo_mode=demo_mode, max_demo_frames=max_frames)
        else:
            run_ansi_app(demo_mode=demo_mode, max_demo_frames=max_frames)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
