

### **Discussion of Milestone 5.3 Outstanding Questions**

Proposed public API for the base `Ruleset` class. This could be defined as an abstract base class or a `Protocol`.

```python
# In Adventorator/rules/engine.py

from typing import Protocol
from .checks import CheckInput, CheckResult
from .dice import DiceRoll

class Ruleset(Protocol):
    """
    Defines the interface for a game system's rules, abstracting away
    the specific mechanics of dice rolling and check resolution.
    """

    def roll_dice(self, expr: str, *, advantage: bool = False, disadvantage: bool = False) -> DiceRoll:
        """
        Parses a dice expression (e.g., '2d6+3') and returns the result.
        Handles advantage/disadvantage on single d20 rolls.
        """
        ...

    def perform_check(self, inp: CheckInput, d20_rolls: list[int] | None = None) -> CheckResult:
        """
        Computes the result of an ability check given a set of inputs.
        If d20_rolls are not provided, it will roll them internally.
        """
        ...

    def get_ability_modifier(self, score: int) -> int:
        """
        Calculates the ability modifier for a given ability score.
        (e.g., score 14 -> +2).
        """
        ...

    def get_proficiency_bonus(self, level: int) -> int:
        """
        Determines the proficiency bonus for a given character level.
        """
        ...
```

**Justification for this API:**

  * `roll_dice`: This replaces the direct use of `DiceRNG`. It encapsulates the random number generator, making it easier to manage seeding for deterministic tests or per-scene stability.
  * `perform_check`: This is the core method from the plan. By allowing optional `d20_rolls`, you can either let the ruleset handle the roll or inject pre-determined rolls for testing or special scenarios.
  * `get_ability_modifier`: The existing `ability_mod` function in `checks.py` is a pure rule calculation. It belongs on the ruleset.
  * `get_proficiency_bonus`: This is a perfect example of system-specific logic. In 5e, it's a simple table based on level. In another system, it might not exist at all. Adding this method makes the ruleset the single source of truth for this value.

#### Confirming the Multi-System Strategy**

For Phase 5, we will hardcode the use of `Dnd5eRuleset` but design the base class interface to allow for future expansion. A factory is not needed yet.*

**Confirmation and Refinement:**

1.  **Use a Protocol or ABC:** The `Ruleset` definition above should be a formal `typing.Protocol` or an `abc.ABC` (Abstract Base Class). This makes the interface explicit and allows static analysis tools like Mypy to verify that any future `Ruleset` (e.g., `Pathfinder2eRuleset`) implements all the required methods.

2.  **Hardcode in `app.py`:** For this phase, you can simply instantiate the `Dnd5eRuleset` at the point of dispatch.

    ```python
    # In Adventorator/app.py, within _dispatch_command

    from Adventorator.rules.engine import Dnd5eRuleset # Or wherever it lives
    ...
    # For now, we only have one ruleset.
    active_ruleset = Dnd5eRuleset()

    inv = Invocation(
        ...
        ruleset=active_ruleset, # Add 'ruleset' to the Invocation dataclass
        ...
    )
    ```

3.  **Future-Proofing:** The next step (beyond Phase 5) would be to add a `system: str` field to your `Campaign` model. The dispatcher would then read `campaign.system` and use a simple dictionary (a "factory map") to select the correct `Ruleset` implementation. You are correct that a full factory pattern is not needed yet.

This strategy correctly prioritizes building one working system first while ensuring the architecture doesn't lock you out of future expansion. It's the right path forward.

---

The focus here is on **action and consequence**. We will prioritize the rules that players directly interact with during the three pillars of play: exploration, social interaction, and especially combat. This is not about building a comprehensive rulebook, but about creating the minimum set of functions needed to make group play feel dynamic and mechanically sound.

-----

### **Proposed Core `Ruleset` MVP Functionality**

This expanded interface goes beyond basic checks to cover the core gameplay loop of combat and character progression.

#### **1. Foundational `Ruleset` Interface**

This includes the methods we discussed previously, forming the bedrock of the engine.

```python
# In Adventorator/rules/engine.py
from typing import Protocol
from .checks import CheckInput, CheckResult
from .dice import DiceRoll

class Ruleset(Protocol):
    """Defines the interface for a game system's core mechanics."""

    # --- Dice & Checks (Already Discussed) ---
    def roll_dice(self, expr: str, *, advantage: bool = False, disadvantage: bool = False) -> DiceRoll: ...
    def perform_check(self, inp: CheckInput, d20_rolls: list[int] | None = None) -> CheckResult: ...
    def get_ability_modifier(self, score: int) -> int: ...
    def get_proficiency_bonus(self, level: int) -> int: ...

    # --- NEW: Core Combat Mechanics ---
    def roll_initiative(self, dex_modifier: int) -> int: ...
    def make_attack_roll(self, attack_bonus: int, *, advantage: bool = False, disadvantage: bool = False) -> AttackRollResult: ...
    def roll_damage(self, damage_dice: str, strength_modifier: int, is_critical: bool = False) -> DamageRollResult: ...

    # --- NEW: Character State & Progression ---
    def apply_damage(self, current_hp: int, damage_amount: int, temp_hp: int = 0) -> tuple[int, int]: ...
    def apply_healing(self, current_hp: int, max_hp: int, healing_amount: int) -> int: ...
```

#### **2. Supporting Data Structures**

You'll need a few simple dataclasses to support the new interface methods. These should live in a new file, `Adventorator/rules/types.py`, to keep the `engine.py` module clean.

```python
# In a new file: Adventorator/rules/types.py
from dataclasses import dataclass

@dataclass(frozen=True)
class AttackRollResult:
    total: int
    d20_roll: int
    is_critical_hit: bool
    is_critical_miss: bool

@dataclass(frozen=True)
class DamageRollResult:
    total: int
    rolls: list[int]
```

-----

### **Justification and `Dnd5eRuleset` Implementation Details**

Here’s why each new function is critical for an MVP and how you'd implement it for D\&D 5e.

#### **Core Combat Mechanics**

This is the most important addition. A multiplayer demo will almost certainly involve combat, and these three methods define the turn-by-turn flow.

**`roll_initiative()`**

  * **Why it's compelling:** Establishes the order of action, a fundamental concept in group combat. It's the first roll everyone makes when a fight breaks out.

  * **`Dnd5eRuleset` implementation:** This is a simple d20 roll plus the character's Dexterity modifier.

    ```python
    # In Dnd5eRuleset
    def roll_initiative(self, dex_modifier: int) -> int:
        # Initiative is a Dexterity check with no proficiency bonus.
        d20_roll = self.roll_dice("1d20").total
        return d20_roll + dex_modifier
    ```

**`make_attack_roll()`**

  * **Why it's compelling:** This is the core "did I hit?" mechanic. It's the most frequent action in combat and directly pits one character against another's Armor Class (AC).

  * **`Dnd5eRuleset` implementation:** A d20 roll plus an attack bonus. A natural 20 is a critical hit, and a natural 1 is a critical miss.

    ```python
    # In Dnd5eRuleset
    def make_attack_roll(self, attack_bonus: int, *, advantage: bool = False, disadvantage: bool = False) -> AttackRollResult:
        roll_result = self.roll_dice("1d20", advantage=advantage, disadvantage=disadvantage)
        d20_roll = roll_result.rolls[-1] # The 'pick' from the d20 roll

        return AttackRollResult(
            total=d20_roll + attack_bonus,
            d20_roll=d20_roll,
            is_critical_hit=(d20_roll == 20),
            is_critical_miss=(d20_roll == 1)
        )
    ```

**`roll_damage()`**

  * **Why it's compelling:** This determines the *consequence* of a successful attack. Rolling a fistful of dice for damage is one of the most satisfying parts of the game for many players.

  * **`Dnd5eRuleset` implementation:** Rolls the specified damage dice expression. On a critical hit, the dice are rolled twice. For melee weapons, the character's Strength modifier is typically added.

    ```python
    # In Dnd5eRuleset
    def roll_damage(self, damage_dice: str, strength_modifier: int, is_critical: bool = False) -> DamageRollResult:
        roll1 = self.roll_dice(damage_dice)
        total_damage = roll1.total + strength_modifier
        all_rolls = roll1.rolls

        if is_critical:
            # On a critical, roll the dice again and add them to the total
            roll2 = self.roll_dice(damage_dice)
            total_damage += roll2.total # Note: Modifiers are NOT added a second time
            all_rolls.extend(roll2.rolls)

        return DamageRollResult(total=max(0, total_damage), rolls=all_rolls)
    ```

#### **Character State & Progression**

These methods make the combat outcomes meaningful by affecting character health.

**`apply_damage()`**

  * **Why it's compelling:** Characters' health is a shared resource and a point of tension. This function makes damage matter by tracking the consequences. It also correctly handles temporary hit points, which is a common mechanic.

  * **`Dnd5eRuleset` implementation:** Damage is first subtracted from temporary HP, then from current HP.

    ```python
    # In Dnd5eRuleset
    def apply_damage(self, current_hp: int, damage_amount: int, temp_hp: int = 0) -> tuple[int, int]:
        damage_to_temp = min(temp_hp, damage_amount)
        new_temp_hp = temp_hp - damage_to_temp
        remaining_damage = damage_amount - damage_to_temp
        new_hp = current_hp - remaining_damage
        return (new_hp, new_temp_hp)
    ```

**`apply_healing()`**

  * **Why it's compelling:** Allows for teamwork and recovery. A multiplayer demo feels more collaborative when one player can heal another.

  * **`Dnd5eRuleset` implementation:** Increases current HP, but not beyond the character's maximum HP.

    ```python
    # In Dnd5eRuleset
    def apply_healing(self, current_hp: int, max_hp: int, healing_amount: int) -> int:
        new_hp = current_hp + healing_amount
        return min(new_hp, max_hp)
    ```