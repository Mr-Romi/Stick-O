# 🥷 Shadow Stickman: Eclipse Duel — Game Guide

> A 30-FPS terminal martial arts fighting game. Run it with:
> ```
> python shadow_stickman.py          # vs AI
> python shadow_stickman.py --demo   # AI vs AI exhibition
> ```

---

## 🕹️ Controls

| Key | Action |
|-----|--------|
| `A` / `←` | Move Left |
| `D` / `→` | Move Right |
| `W` / `↑` | Jump |
| `S` / `↓` | **Crouch / Block** (hold to guard) |
| `E` | **Dash** (tap while holding A or D to dash that direction) |
| `J` | **Punch** |
| `K` | **Kick** |
| `L` | **Weapon / Ranged Attack** |
| `U` | **Shadow Ability** (costs 50 Shadow Energy) |
| `I` | **Unleash Shadow Form** (requires ≥ 50 Shadow Energy) |
| `1` | Switch to Barehanded style |
| `2` | Switch to Shadow Katana style |
| `3` | Switch to Blood Kusarigama style |
| `P` | Pause / Move List |
| `Q` | Quit to Title / Exit |

---

## ⚔️ Move List

Moves change depending on your **stance** and **direction held** when you press the attack button.

### Punch — `J`
| Situation | Move | Damage |
|-----------|------|--------|
| Neutral (on ground) | Shadow Jab | 6 |
| Forward held | Heavy Cross | 11 |
| Crouching (`S`) | Rising Dragon Uppercut | 14 ⬆️ Launcher |
| In the air | Flying Shadow Kick | 14 |

### Kick — `K`
| Situation | Move | Damage |
|-----------|------|--------|
| Neutral (on ground) | Snap High Kick | 12 |
| Forward held | Spinning Roundhouse | 18 💥 Knockdown |
| Crouching (`S`) | Shadow Leg Sweep | 10 💥 Knockdown |
| In the air | Flying Shadow Kick | 14 |

### Weapon — `L`
| Style | Situation | Move | Damage |
|-------|-----------|------|--------|
| Shadow Katana | Neutral | Iaido Crescent Slash | 16 |
| Shadow Katana | Forward held | Helm Splitter (Overhead) | 22 💥 Knockdown |
| Blood Kusarigama | Any | Kusarigama Chain Lash | 15 (long reach!) |
| Barehanded / Crouching | Any | **Shadow Kunai Throw** | 8 (projectile) |
| In the air | Any | Shadow Kunai Throw | 8 (projectile) |

### Shadow Abilities — `U` (costs **50 Shadow Energy**)
| Situation | Ability | Damage |
|-----------|---------|--------|
| Standing | **Void Blink Assassination** — teleports toward opponent | 28 💥 Knockdown |
| Crouching (`S`) | **Abyssal Pillar Eruption** — ground shockwave | 26 💥 Knockdown |

> [!IMPORTANT]
> Shadow Abilities have **invulnerability frames** during startup — you cannot be hit while activating them.

---

## 🛡️ Defense System

### Basic Guard
- **Hold `S`** (or hold back while walking) to guard.
- Blocking reduces damage to a **small chip** (~18% of base damage).
- Low attacks (Sweep) **bypass standing guard** — crouch-block with `S`.
- Overhead attacks (Helm Splitter, Roundhouse) **bypass crouch guard** — stand-block.

### Just-Frame Parry ⚡
- If you start blocking within the **first 3 frames** of being hit, you execute a **Parry**:
  - You take **zero damage**.
  - The attacker is thrown into **hitstun** (reversed).
  - You gain **+15 Shadow Energy**.

### Invulnerability Windows
| Action | Invul Frames |
|--------|-------------|
| Knockdown (early frames) | Full invulnerability for first 3 timer ticks |
| Dash | Invulnerable while `state_timer ≥ 3` |
| Shadow Abilities | Invulnerable during startup frames |

---

## 💜 Shadow System

The **Shadow Energy bar** (bottom bar, shown as %) fills as you fight.

| Action | Shadow Gain |
|--------|-------------|
| Landing a hit | + move's `shadow_gain` value |
| Getting hit (defender) | + 55% of move's `shadow_gain` |
| Blocking a hit | + 25% of move's `shadow_gain` |
| Parrying | **+15 flat** |

### Shadow Form — `I`
Requires ≥ 50 Shadow Energy. Activating it:
- Drains energy continuously (0.45 per frame).
- **1.4× damage** on all attacks.
- **Speed boost** (movement + attack momentum × 1.35).
- **25% lifesteal** — every hit you land heals you.
- Glowing magenta aura particles appear.
- Ends automatically when energy hits 0.

---

## 🥊 Combat Mechanics

### Combo Scaling
Long combos deal progressively less damage:
- Each consecutive hit reduces damage by **10%**, down to a minimum of **45%**.
- The combo counter resets after **32 frames** of no contact.

### Counter Hit
If you hit an opponent **during their startup frames** (before their attack becomes active):
- **1.25× damage multiplier**.
- +3 extra hitstun frames.
- Displayed as `COUNTER!` floating text.

### Combo Cancel
You can cancel a **connected Jab** (`Shadow Jab`) into:
- Heavy Cross, Uppercut, High Kick
- Katana Slash (if equipped)
- Kusarigama Lash (if equipped)

### Knockdown & Wakeup
- Knockdown attacks (Sweep, Roundhouse, Uppercut, Shadow Abilities) floor the opponent.
- They are **invulnerable** for the first few frames on the ground.
- After the timer expires, they automatically return to Idle.

### Pushbox
Fighters **cannot overlap** — they physically push each other apart, creating pressure and corner situations.

---

## 🗡️ Weapon Styles

Switch styles mid-fight with `1`, `2`, `3`:

| Style | Key | Best For |
|-------|-----|----------|
| **Barehanded** | `1` | Fast combo-focused play; L fires Kunai |
| **Shadow Katana** | `2` | Balanced; long-range slash + Overhead mix |
| **Blood Kusarigama** | `3` | **Longest melee reach** in the game (reach = 19) |

> [!TIP]
> Switch to Barehanded just to throw a Kunai mid-combo, then switch back to your main weapon style!

---

## 🏆 Match Structure

- **Best of 3 rounds** — first to win 2 rounds wins the match.
- Each round has a **99-second timer**.
- If time runs out, the fighter with more HP wins the round.
- If both fighters are KO'd simultaneously → **DOUBLE K.O.** (no round awarded).
- Press `R` after a match ends to **Rematch**.

---

## 🤖 AI Difficulty

Select before the match starts with `1`, `2`, or `3`:

| Level | Name | Behavior |
|-------|------|----------|
| 1 | Initiate (Easy) | Slow reactions, simple patterns |
| 2 | Ronin (Medium) | Balanced spacing + occasional combos |
| 3 | Shadow Master (Hard) | Fast reactions, combos, shadow abilities, parries |

---

## 💡 Tips & Strategy

- **Jab into Cross** is your bread-and-butter combo — fast startup, easy to confirm.
- **Sweep** is unblockable while standing (low attack) — mix with overheads to open guards.
- **Dash** through projectiles (invulnerability frames).
- **Shadow Form lifesteal** can let you win a close round by recovering HP while dealing damage.
- The AI always reacts to your attacks — bait a defensive reaction, then tick-throw with Kunai.
- Watch the opponent's `block_frames` — hit them right as they start blocking to bait a whiff-punish.
