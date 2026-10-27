# 🥷 Shadow Stickman: Eclipse Duel — Game Guide

<!-- Uploading "shadow_stickman_gameplay.mp4"... -->

> A 30-FPS terminal martial arts fighting game. No external dependencies.
> ```
> python shadow_stickman.py                  # Title screen, then play vs AI
> python shadow_stickman.py --demo           # AI vs AI exhibition
> python shadow_stickman.py --demo --seed=7  # Same exhibition, reproducible
> python shadow_stickman.py --test           # Built-in self-diagnostic test suite
> ```
> Other options: `--ansi` (force the ANSI renderer instead of curses) and `--frames=N` (stop after N frames).
> Works on Windows (PowerShell / CMD), Linux and macOS. Python 3.7+ recommended; a terminal of roughly 104×28 or larger.

---

## 🕹️ Controls

### In a match

| Key | Action |
|-----|--------|
| `A` / `←` | Move Left |
| `D` / `→` | Move Right |
| `W` / `↑` | Jump (press `A`/`D` in the air to steer) |
| `S` / `↓` | **Crouch / Block** (hold to guard) |
| `E` | **Dash** (toward the direction you hold, or toward your opponent if none) |
| `J` | **Punch** |
| `K` | **Kick** |
| `L` | **Weapon / Ranged Attack** |
| `U` | **Shadow Ability** (costs 50 Shadow Energy, grounded only) |
| `I` | **Unleash Shadow Form** (requires ≥ 50 Shadow Energy) |
| `1` / `2` / `3` | Switch style: Barehanded / Shadow Katana / Blood Kusarigama |
| `P` | Pause / Move List |
| `Q` | Quit to Title |
| `R` | Rematch (after a match ends) |

### Title screen

| Key | Action |
|-----|--------|
| `1` / `2` / `3` | Select AI difficulty (the same keys switch weapon style once a match starts) |
| `Enter` / `Space` | Start a 1-player duel vs AI |
| `V` | Watch an AI vs AI exhibition |
| `Q` | Exit |

> [!NOTE]
> Terminals report key **presses and auto-repeats**, not key releases. To keep guarding, crouching and walking smooth, held move/guard keys (`A`, `D`, `S`, arrows) stay active for 3 frames after the last key event. Pressing the opposite direction overrides this instantly. Inputs pressed during a hit-freeze (hitstop) are saved and used as soon as it ends, so combo cancels are forgiving.

---

## ⚔️ Move List

Moves change depending on your **stance** and **direction held** when you press the attack button.

**Attack heights** decide how they interact with guarding and crouching:

| Type | Effect |
|------|--------|
| **High** | Whiffs completely against a **crouching** opponent. |
| **Mid** | Hits standing and crouching opponents; blocked by either guard. |
| **Low** | Bypasses **standing** guard; you must crouch-block it. |
| **Overhead** | Bypasses **crouch** guard; you must stand-block it. |

### Punch — `J`
| Situation | Move | Damage | Type |
|-----------|------|--------|------|
| Neutral (on ground) | Shadow Jab | 6 | Mid |
| Forward held | Heavy Cross | 11 | Mid |
| Crouching (`S`) | Rising Dragon Uppercut | 14 ⬆️ Launcher + knockdown | Mid |
| In the air | Flying Shadow Kick | 14 | Overhead |

### Kick — `K`
| Situation | Move | Damage | Type |
|-----------|------|--------|------|
| Neutral (on ground) | Snap High Kick | 12 | **High** |
| Forward held | Spinning Roundhouse | 18 💥 Knockdown | **High** |
| Crouching (`S`) | Shadow Leg Sweep | 10 💥 Knockdown | **Low** |
| In the air | Flying Shadow Kick | 14 | Overhead |

### Weapon — `L`
| Situation | Move | Damage | Type |
|-----------|------|--------|------|
| Crouching (any style) | **Shadow Kunai Throw** | 8 (projectile) | Projectile |
| In the air (any style) | Shadow Kunai Throw | 8 (projectile) | Projectile |
| Barehanded | Shadow Kunai Throw | 8 (projectile) | Projectile |
| Katana, neutral | Iaido Crescent Slash | 16 | Mid |
| Katana, forward held | Helm Splitter | 22 💥 Knockdown | Overhead |
| Kusarigama, standing | Kusarigama Chain Lash | 15 (long reach!) | Mid |

### Shadow Abilities — `U` (costs **50 Shadow Energy**, must be on the ground)
| Situation | Ability | Damage | Type |
|-----------|---------|--------|------|
| Standing | **Void Blink Assassination** — blinks toward the opponent | 28 💥 Knockdown | Overhead |
| Crouching (`S`) | **Abyssal Pillar Eruption** — ground shockwave | 26 💥 Knockdown | Low |

> [!IMPORTANT]
> Shadow Abilities are **invulnerable during their startup frames** — you cannot be hit while activating them.

---

## 🛡️ Defense System

### Basic Guard
- **Hold `S`** (or hold back while walking) to guard.
- A successful block reduces damage to a **small chip** (about 18% of base damage, minimum 1) and shoves you back slightly.
- **Low** attacks (Leg Sweep, Pillar Eruption) bypass standing guard — crouch-block with `S`.
- **Overhead** attacks (Helm Splitter, Flying Shadow Kick, Void Blink) bypass crouch guard — stand-block.
- **High** attacks (High Kick, Roundhouse) cannot hit a crouching opponent at all, so crouching also works as a dodge.
- **Kunai** can be blocked with any guard.

### Just-Frame Parry ⚡
If your guard is **valid for the attack** and you started it **within the last 3 frames** before the hit lands, you execute a **Parry**:
- You take **zero damage**.
- A parried melee attacker is thrown into **hitstun** (reversed).
- A parried **Kunai** is destroyed (the thrower is not stunned).
- You gain **+15 Shadow Energy**.

Holding guard early only gives a normal block — tap or start guarding just before the hit to parry.

### Invulnerability Windows
| Action | Invulnerable for |
|--------|------------------|
| Dash | The first 3 frames of the 5-frame dash |
| Shadow Abilities | Their entire startup (Void Blink 4 frames, Pillar Eruption 5 frames) |
| Knockdown | Almost the whole knockdown (15 of its 18 frames); you can't be hit while on the floor |

Attacks and Kunai pass straight through an invulnerable fighter. Dashing through a Kunai works for this reason.

---

## 💜 Shadow System

The **Shadow Energy bar** (shown as %) fills as you fight.

| Event | Shadow Energy |
|-------|---------------|
| You land a hit | + the move's `shadow_gain` value *(not while in Shadow Form)* |
| Your attack is blocked | + 35% of the move's `shadow_gain` *(not while in Shadow Form)* |
| You get hit | + 55% of the move's `shadow_gain` |
| You block a hit | + 25% of the move's `shadow_gain` |
| You parry | **+15 flat** |

Shadow Abilities give no energy when they hit.

### Shadow Form — `I`
Requires ≥ 50 Shadow Energy (the activation itself is free). While active:
- Energy drains continuously (0.45 per frame — about 7 seconds from a full bar).
- **1.4× damage** on all attacks, including Kunai.
- **Speed boost** (movement, dash and attack momentum, about ×1.35).
- **25% lifesteal** — damage you deal heals you, including chip damage on blocked hits.
- You **don't gain Shadow Energy from hitting** while it's active.
- Glowing magenta aura particles appear.
- Ends automatically when energy reaches 0. Using a Shadow Ability (50 energy) while in Shadow Form burns the bar fast.

---

## 🥊 Combat Mechanics

### Trades
If both fighters' attacks connect on the same frame, **both hits land**. Neither player has priority.

### Hitstop
Heavier hits briefly freeze both fighters (1–3 frames) for impact. Inputs you press during the freeze are buffered and used right after.

### Combo Scaling
Long combos deal progressively less damage:
- Each consecutive hit reduces damage by **10%**, down to a minimum of **45%**.
- Kunai hits count toward the combo too.
- The combo counter resets after **32 frames** of no contact.

### Counter Hit
If you land an unblocked hit **during the opponent's startup frames** (before their attack becomes active):
- **1.25× damage multiplier**.
- +3 extra hitstun frames.
- Displayed as `COUNTER!` floating text.
- Applies to Kunai as well as melee.

### Combo Cancel
You can cancel a **connected Shadow Jab** into:

| Cancel into | Input |
|-------------|-------|
| Heavy Cross | `J` |
| Rising Dragon Uppercut | `S` + `J` |
| Snap High Kick | `K` |
| Iaido Crescent Slash (Katana equipped) | `L` |
| Kusarigama Chain Lash (Kusarigama equipped) | `L` |

Roundhouse (forward `K`) and Helm Splitter (forward `L`) cannot be cancelled into.

### Knockdown & Wakeup
- Knockdown attacks (Uppercut, Roundhouse, Leg Sweep, Helm Splitter and both Shadow Abilities) floor the opponent, as does any killing blow.
- A downed fighter is invulnerable for most of the knockdown, so you can't hit them while they're on the floor.
- When the timer expires they automatically return to Idle.

### Pushbox
Fighters **cannot overlap** — they physically push each other apart, creating pressure and corner situations.

---

## 🗡️ Weapon Styles

Switch styles mid-fight with `1`, `2`, `3`:

| Style | Key | Best For |
|-------|-----|----------|
| **Barehanded** | `1` | Fast combo-focused play; `L` throws a Kunai |
| **Shadow Katana** | `2` | Balanced; long-range slash + Overhead mix |
| **Blood Kusarigama** | `3` | **Longest weapon reach** (reach = 19) |

> [!TIP]
> Crouching and pressing `L` throws a Kunai in **any** style, so you never need to swap styles just to throw one.

---

## 🏆 Match Structure

- **Best of 3 rounds** — first to win 2 rounds wins the match.
- Each round has a **99-second timer**.
- If time runs out, the fighter with more HP wins the round. **Equal HP is a draw.**
- If both fighters are KO'd simultaneously → **DOUBLE K.O.** (no round awarded).
- Press `R` after a match ends to **Rematch**.

---

## 🤖 AI Difficulty

Select before the match starts with `1`, `2`, or `3` on the title screen:

| Level | Name | Behavior |
|-------|------|----------|
| 1 | Initiate (Easy) | Attacks rarely; reacts to your attacks about half the time (≈50%) |
| 2 | Ronin (Medium) | Balanced spacing and occasional combos; reacts ≈72% of the time |
| 3 | Shadow Master (Hard) | Attacks often, uses Shadow Abilities more, reacts ≈94% of the time |

When the AI reacts it guards (crouching against lows). It has no dedicated parry logic, so a parry only happens if its guard happens to land in the parry window.

---

## 💡 Tips & Strategy

- **Jab into Cross** is your bread-and-butter combo — fast startup, easy to confirm.
- **Open guards with mix-ups:** standing guard loses to Sweep, crouch guard loses to Helm Splitter or Flying Kick.
- **Crouch against High Kick and Roundhouse** — they whiff completely. Punish their long recovery.
- **Dash through attacks and Kunai** — you're invulnerable for the first 3 frames.
- **Parry by timing, not by holding:** start your guard just before the hit lands.
- **Same-frame hits trade.** Prefer fast, safe moves when the exchange is close.
- **Shadow Form lifesteal** can win a close round: deal damage (even chip on a block) to recover HP.
- **Bait the AI:** it doesn't always react, especially on lower levels. Throw a Kunai to draw a guard, then switch to a low or overhead.
- **Kunai are real combo pieces now:** they scale, can counter-hit, and parried Kunai vanish, so don't throw them into a ready guard.
