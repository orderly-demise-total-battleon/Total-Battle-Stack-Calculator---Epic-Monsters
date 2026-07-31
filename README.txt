==============================================================================
                     TOTAL BATTLE STACK CALCULATOR
==============================================================================

Works out how many of each unit to field so your army dies in the order you
want it to, and shows you what each option costs.

Built for planning epic monster hits, but it works for anything where you
care about which of your stacks gets destroyed first.


------------------------------------------------------------------------------
THE IDEA IN ONE PARAGRAPH
------------------------------------------------------------------------------

In battle, the stack with the highest total stack HP dies first. Stack HP is
just "quantity x effective HP per unit". That means you control the death
order by controlling quantities: field a weak unit in bulk and it soaks the
opening hits, while your genuinely tanky units survive to keep swinging. The
calculator picks quantities so each successive stack sits just below the one
before it, in one continuous chain from first-to-die to last.

One deliberate exception: siege engines are forced to the front regardless
of their HP. Their real combat strength isn't reflected by their HP stat, so
they're used as cannon fodder to buy extra attacks for the units behind them.

Your catapult tiers go first. The game also offers each account one
Authority-funded siege mercenary for its level (Palintone, Trebuchet, others
higher up); the tool finds it automatically by its Siege Engine tag, so there
is nothing to configure. It slots into the gap between your highest-eff-HP
siege unit and your highest non-siege Leadership stack. If no quantity fits
that gap it is left out of the army entirely rather than fielded late.


------------------------------------------------------------------------------
WHAT THIS TOOL DOES NOT DO
------------------------------------------------------------------------------

Be clear on this before you trust it for anything:

  * No damage or strength simulation. It knows base HP, unit types, your
    health bonuses, and troop capacity costs. It has no STR data at all. It
    cannot tell you whether you win a fight.

  * No turn order or attack priority. It does not model which enemy unit
    swings at which of your stacks, or in what order within a round.

  * It assumes each enemy "squad" destroys exactly one of your stacks. That
    is the model behind the recovery-cost numbers. If that is not how your
    target behaves, the cost figures won't mean what you think.

It is a stack-composition tool. It answers "how do I arrange my army", not
"do I win".


------------------------------------------------------------------------------
SETUP
------------------------------------------------------------------------------

You need Python 3. No libraries, no install - it is one file.

    python tb_stack_calc.py

Then edit the caps at the bottom of the file, or import it:

    from tb_stack_calc import refit_trajectory, print_squad_trajectory
    from tb_stack_calc import PERMANENT_BONUS_RULES

    out = refit_trajectory(leadership, dominance, authority,
                           PERMANENT_BONUS_RULES, recovery_n=4)
    print_squad_trajectory(out)

ARGUMENT ORDER TRAP: the signature is (leadership, dominance, authority).
The game screen usually shows Leadership, Authority, Dominance. Map them by
name, not by the order you read them, or you will silently swap two pools and
get a plausible-looking but wrong stack.

recovery_n should equal the number of squads your target has - that is how
many of your stacks will be destroyed.


------------------------------------------------------------------------------
YOU MUST DO THIS FIRST: PUT IN YOUR OWN NUMBERS
------------------------------------------------------------------------------

The values shipped in this file belong to someone else's account. Run it
unmodified and you will get a confident, precise, wrong answer. There are
three things to replace, all near the top of tb_stack_calc.py.


1. YOUR PERMANENT HEALTH BONUSES

Find the "ACCOUNT CONFIGURATION" banner. Total up each bucket from every
source you have - Army Modernization, Clan Research, Hero Talents, VIP, Hall
of Fame, City Customization, Monsters Boost, personal bonuses, battle
accessories - and write the totals in.

A unit collects EVERY bucket it matches, added together:

    {"pp": 150}                             every unit (flat army health)
    {"pp": 80, "subtype": "Guardsman"}      Guardsman-subtype units only
    {"pp": 200, "combat_class": "Ranged"}   anything tagged Ranged

So an Archer (Guardsman + Ranged) gets all three. Effective HP is
base_hp x (1 + total_pct/100). Omit any bucket that is zero for you.

    Subtypes:        Guardsman, Specialist, Engineer, Monster
    Combat classes:  Mounted, Melee, Ranged, Flying, Siege Engine,
                     Beast, Dragon, Elemental, Giant


2. YOUR HERO

HERO_BONUS_RULES holds hero-granted HEALTH bonuses, kept separate so that
switching heroes is a one-line change to ACTIVE_HERO.

If your hero's bonus is strength, leadership capacity, production, or
anything else this tool doesn't model, give it an EMPTY list. That is correct
and complete - don't invent a health number for it.


3. YOUR RECOVERY DIVISOR

GOLD_RECOVERY_REDUCTION converts raw capacity cost into real gold. It scales
with your Temple level, so it differs per player and rises as you upgrade.

To find yours: lose a stack, note the gold the game quotes to revive it, and
solve for the divisor. Check it against two or three different unit types.

Get this wrong and every gold figure is wrong by a constant factor - the
rankings still hold, but the numbers don't.


4. YOUR ROSTER, IF IT DIFFERS

build_units() lists every unit with its base HP, subtype, combat class and
capacity cost. If you haven't unlocked a tier, delete the line. If you have
units that aren't listed, add them to the matching list following the same
pattern. Mercenaries go in mercs_no_emh, monsters in monsters_m3 through
monsters_m6.

Base HP values are universal game data, so the ones here should be right for
anyone - it is the SET of units you own that differs.


------------------------------------------------------------------------------
READING THE OUTPUT
------------------------------------------------------------------------------

    Catapult tiers                     Squads  Dominance %  FULL L+D  first-N
    ---------------------------------  ------  -----------  --------  -------
    Ballistae VI                           22        98.4%    98,116   15,685
    Ballistae VI, Cat V                    23        96.0%    96,947    7,389
    Ballistae VI, Cat V, Cat IV            23        99.9%    98,823    4,703

One row per catapult configuration. For each, the tool re-optimises your
infantry roster from scratch, so the rows are genuinely comparable.

  Squads       How many separate stacks you field. More squads means a
               limited-hit enemy burns its attacks on more cheap stacks
               before reaching your good units.

  Dominance %  How much of your Dominance pool you actually used. Leftover
               Dominance is wasted army.

  FULL L+D     Gold to recover your ENTIRE Leadership + Dominance army.
               Barely moves between rows - it mostly tracks how full your
               pools are.

  first-N      Gold to recover the first N stacks destroyed. THIS IS WHAT
               THE FIGHT ACTUALLY COSTS YOU. Varies enormously by row.

  Rule         How the row was chosen (see below).


HOW A ROW GETS CHOSEN

For each catapult configuration the tool sweeps your infantry roster from
wide to narrow. Narrower rosters push more capacity into fewer stacks, which
raises the ceilings the Dominance tiers hang off, which raises Dominance
usage.

It then takes the widest roster that still fills Dominance, and checks
whether going one squad wider stays within 5 percentage points of full. If it
does, it takes the extra squad. That is the "+1 squad" tag.

Rows marked "NEVER SATURATES" could not fill Dominance at any roster width.
TREAT THOSE AS DISQUALIFIED, not as options - they will sometimes show a high
squad count while wasting a third of your Dominance pool.


PICKING BETWEEN THE ROWS

A reasonable default: most squads first, then the most catapult tiers as a
tie-break - more catapult tiers means more of the opening hits land on siege
before anything valuable dies. Ignore disqualified rows entirely.

But look at first-N before you commit. The extra squad sometimes costs three
times the recovery, and if it isn't buying you anything against that specific
target, the cheaper row is the better army.

Once you have picked a row, print the full stack:

    entry = out["catapult_trajectory"][2]      # whichever row you want
    print_report(entry["result"])
    print_full_death_order(entry["result"])


------------------------------------------------------------------------------
THINGS THAT LOOK WRONG BUT AREN'T
------------------------------------------------------------------------------

ORDERING FLAGS IN THE DEATH ORDER

print_full_death_order() marks any stack that doesn't sit strictly below the
one before it. Some of these are expected by design:

  * ties or swaps WITHIN the M4, M5 or M6 tiers
  * anything involving mercenaries against M5 / M6
  * exact ties between units with identical effective HP

Those groups are deliberately unordered. A flag BETWEEN named units -
catapults vs infantry, Palintone vs catapults, a Griffin vs the tier it
interleaves with - is a real problem worth investigating.

A HUGE GAP BETWEEN THE LAST CATAPULT AND THE FIRST INFANTRY STACK

Expected. Catapults are a ceiling bolted on top of the chain, not a
continuation of it.

LEFTOVER CAPACITY IN ONE POOL

Dominance is usually limited by the ceiling above it, not by budget. You can
have thousands of spare Dominance that is literally unspendable because every
tier is blocked. The fix is a narrower infantry roster, which raises the
whole cascade - not more monsters.

A UNIT'S QUANTITY FALLING AFTER YOU GAIN A BONUS

Correct. Higher effective HP per unit means fewer bodies are needed to hold
the same position in the chain.


------------------------------------------------------------------------------
USING THIS WITH AN AI ASSISTANT
------------------------------------------------------------------------------

This is probably the easiest path. Give the assistant tb_stack_calc.py and
this README, then tell it:

  * your bonus totals, bucket by bucket
  * which hero you have equipped and what it does
  * your Leadership / Dominance / Authority caps
  * your target's squad count
  * any one-time captain or equipment bonuses for that specific run

One-time bonuses get added on top of the permanent ones for a single run,
rather than edited into the file:

    RULES = PERMANENT_BONUS_RULES + [
        {"pp": 250, "subtype": "Monster"},
        {"pp": 100, "combat_class": "Mounted"},
    ]

Ask it to edit the config section, run the trajectory, and show you the full
stack for the row you pick. Tell it explicitly that the shipped bonus values
are not yours - otherwise it may leave them in place.


------------------------------------------------------------------------------
A WARNING ABOUT THIN MARGINS
------------------------------------------------------------------------------

The calculator regularly produces stacks where consecutive stack HPs differ
by well under 1%. That is the point - tight chains waste less capacity.

It also means the stack is unforgiving of miscounts. If you field even a few
units fewer than the number given, two stacks can swap places and the wrong
one takes the first hit. When the output shows stacks within a percent of
each other, field the exact quantities and check them in-game before
committing.
