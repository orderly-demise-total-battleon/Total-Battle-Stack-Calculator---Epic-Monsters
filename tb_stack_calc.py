"""
Total Battle stacking calculator.

Given your Leadership / Dominance / Authority caps and your permanent health
bonuses, this works out how many of each troop type to field so that the army
dies in a deliberately chosen order.

CORE RULE: in battle, the stack with the HIGHEST total stack HP dies first.
Stack HP = quantity x per-unit effective HP. So a unit with LOW effective HP
fielded in bulk soaks the first hits, letting your naturally tanky units survive
to keep fighting. The calculator picks quantities so that each successive stack
sits just below the one before it.

The chain it builds, first to die -> last:
  catapults -> Palintone -> regular infantry -> M3 monsters (with Epic Monster
  Hunter interleaved) -> Battle Griffin V -> M4 -> Battle Griffin VI -> M5 ->
  M6 -> remaining mercenaries

Catapults and Palintone are deliberate exceptions to the low-HP-dies-first rule:
their real combat strength is not reflected by their HP stat, so they are forced
to the front as cannon fodder, buying extra attacks for the units behind them.

SEE README.md for how to configure this for your account and how to read the
output. You MUST replace the bonus values near the top of this file with your
own -- the ones that ship here belong to a different account.

Run: python tb_stack_calc.py   (edit the caps at the bottom of the file)
"""
import math


# ============================================================================
# ACCOUNT CONFIGURATION -- THIS IS THE PART YOU MUST EDIT
# ============================================================================
# Everything below this banner describes ONE player's account. The numbers that
# ship with this file are a working example, NOT defaults that will be correct
# for you. Replace them with your own before trusting any output.
#
# Read your own values off the in-game research/bonus screens and total them per
# bucket. Each bucket is expressed in percentage points (pp) of bonus HEALTH.
# A unit's effective HP = base_hp * (1 + total_bonus_pct / 100).
#
# HOW BUCKETS COMBINE: a unit picks up EVERY rule it matches, added together.
#   - a rule with no filter applies to every unit (the flat "army health" bucket)
#   - {"subtype": "Guardsman"} applies only to Guardsman-subtype units
#   - {"combat_class": "Ranged"} applies only to units tagged Ranged
# So an Archer (Guardsman + Ranged) gets army + Guardsman + Ranged.

# --- Hero-conditional bonuses ------------------------------------------------
# Bonuses granted by whichever hero is equipped, kept SEPARATE from the
# account-level list so switching heroes is a one-line change rather than a
# hand-edit of the totals.
#
# IMPORTANT: this dict holds HEALTH bonuses only. A hero whose effect is on
# strength, leadership capacity, resource production or anything else this
# HP-only tool does not model gets an EMPTY list -- that is the correct and
# complete answer, not a placeholder for missing data.
HERO_BONUS_RULES = {
    # Example: a hero trait granting +200pp Engineer health (it also grants
    # +200pp Engineer strength, which this tool does not model -- see "What this
    # tool does not do" in the README).
    "Matemhain": [
        {"pp": 200, "subtype": "Engineer"},
    ],
    # Example: a hero whose bonus is strength-only, so nothing to model here.
    "Meriones": [],
}

# Which hero is equipped right now. Switching heroes = change this one line.
ACTIVE_HERO = "Meriones"

# --- Account-level permanent bonuses ----------------------------------------
# Sum each bucket from all its sources: Army Modernization, Clan Research, Hero
# Talents, VIP, Hall of Fame, City Customization, Monsters Boost, personal
# bonuses, and any battle accessory that grants health. Hero-granted bonuses do
# NOT belong here -- put those in HERO_BONUS_RULES above.
#
# Buckets you can use: no filter (flat) | subtype Guardsman / Specialist /
# Engineer / Monster | combat_class Mounted / Melee / Ranged / Flying /
# Siege Engine / Beast / Dragon / Elemental / Giant.
# Omit a bucket entirely if it is zero for you.
_ACCOUNT_BONUS_RULES = [
    # Flat "army health" -- applies to every unit you field. If part of this
    # total comes from a conditional source (e.g. a dragon accessory you tick on
    # before battle), subtract it on any run where that source is absent.
    {"pp": 163.5},

    # Subtype buckets
    {"pp": 86.0, "subtype": "Guardsman"},
    {"pp": 85,   "subtype": "Specialist"},
    {"pp": 150,  "subtype": "Engineer"},

    # Combat-class buckets. Note these three are often close together but rarely
    # identical -- when two are exactly equal, same-base-HP units of those
    # classes tie exactly in effective HP. Ties are handled correctly.
    {"pp": 203.5, "combat_class": "Mounted"},
    {"pp": 192.5, "combat_class": "Melee"},
    {"pp": 203.5, "combat_class": "Ranged"},
    {"pp": 182.5, "combat_class": "Flying"},
    {"pp": 346,   "combat_class": "Siege Engine"},

    # Monster-type buckets. These are per-unit bonuses on monsters carrying the
    # tag -- do not confuse a "Dragon health" bucket here with a flat army-health
    # bonus that happens to come from a dragon source.
    {"pp": 19.5, "combat_class": "Beast"},
    {"pp": 19.5, "combat_class": "Dragon"},
    {"pp": 19.5, "combat_class": "Elemental"},
    {"pp": 19.5, "combat_class": "Giant"},
]

# The bonus set every real stack calculation should pass as stack_bonus_pct: account-level
# bonuses plus whatever the currently-equipped hero contributes. Extend with a list entry
# for a one-off captain/equipment bonus when one applies for a specific run, e.g.
# PERMANENT_BONUS_RULES + [{"pp": one_off_pct}]. Not passed as a function default
# (explicit is safer, esp. since the Army Health total is conditional on fielding a
# dragon -- see the note above).
if ACTIVE_HERO not in HERO_BONUS_RULES:
    raise ValueError(
        f"ACTIVE_HERO is {ACTIVE_HERO!r}, which has no entry in HERO_BONUS_RULES "
        f"(known heroes: {sorted(HERO_BONUS_RULES)}). Add the hero's health bonuses "
        f"there -- an empty list is correct for a hero whose bonus is strength-only."
    )
PERMANENT_BONUS_RULES = _ACCOUNT_BONUS_RULES + HERO_BONUS_RULES[ACTIVE_HERO]


def eff(base, bonus_pct):
    return round(base * (1 + bonus_pct / 100))


def resolve_extra_bonus(bonus_input, subtype, combat_class):
    """bonus_input is either a flat number (applies to every unit, e.g. a plain
    'army health' bonus -- backward compatible with the old stack_bonus_pct
    behavior) or a list of conditional rules: {"pp": <float>, "subtype": <str,
    optional>, "combat_class": <str, optional>}. A rule's pp is added if the
    unit's subtype matches (when given) AND the unit carries the named combat
    class tag (when given) -- omitting a filter means it matches everyone on
    that axis. Multiple matching rules stack additively."""
    if isinstance(bonus_input, (int, float)):
        return bonus_input
    total = 0
    for rule in bonus_input:
        if "subtype" in rule and rule["subtype"] != subtype:
            continue
        if "combat_class" in rule and rule["combat_class"] not in combat_class:
            continue
        total += rule["pp"]
    return total


def build_units(r, include_catapult_ii=False, include_catapult_i=False, exclude_catapult_names=None):
    """r = stack-time bonus. Either a flat number (applied to every unit alike --
    e.g. a plain "army health" bonus) or a list of conditional rules (see
    resolve_extra_bonus) for bonuses that only apply to a Subtype and/or Combat
    Class, e.g. [{"pp": 64}, {"pp": 230.5, "subtype": "Monster"}, {"pp": 102,
    "combat_class": "Mounted"}] for "army 64pp + monster 230.5pp + mounted 102pp".
    include_catapult_ii: add Catapult II (base HP 2,700) below Catapult III.
    include_catapult_i: add Catapult I (base HP 1,500) below Catapult II (implies
    include_catapult_ii). Both assume Lead cost 10 to match III/IV/V -- not
    confirmed data, flag if wrong. exclude_catapult_names: remove named catapult
    tiers from the pool entirely (e.g. ["Catapult III"]) -- the catapult-side
    analogue of exclude_names for infantry; lets a caller test "drop the cheapest
    catapult tier" the same way the infantry sweep drops cheap infantry. Caller's
    responsibility not to exclude every catapult tier (empty pool breaks the
    Leadership search, same known gap as excluding all infantry)."""

    def bonus(subtype, combat_class, research_pct):
        # research_pct (the value passed in per unit() call below) is now VESTIGIAL --
        # snapshot of Army + subtype + combat_class bonuses (near-exact 16.5pp gap vs
        # PERMANENT_BONUS_RULES across almost every unit), so adding it on top of the
        # fresh disaggregated totals counted most bonuses twice. PERMANENT_BONUS_RULES
        # is now the sole source of bonus_pct. research_pct is kept as an argument (not
        # stripped from the ~35 unit() call sites below) purely as a historical record
        # of the old snapshot value -- it contributes nothing to eff_hp.
        return resolve_extra_bonus(r, subtype, combat_class)

    def unit(name, base_hp, subtype, combat_class, research_pct, **cost):
        bonus_pct = bonus(subtype, combat_class, research_pct)
        return {
            "name": name, "base_hp": base_hp, "subtype": subtype, "combat_class": combat_class,
            "bonus_pct": bonus_pct, "eff_hp": eff(base_hp, bonus_pct), **cost,
        }

    regular_infantry = [
        # roster below tier III for large squad_count searches (find_squad_maximizing_stack)
        # -- Lead cost 1 is an ASSUMPTION matching their III/IV/V tier-mates, not confirmed
        # data; flag if wrong. research_pct also assumed to match tier-mates (vestigial,
        # doesn't affect eff_hp either way -- see note above).
        unit("Archer II",        270,   "Guardsman",  ["Ranged"],         315,   lead=1),
        unit("Swordsman II",     270,   "Specialist", ["Melee"],          313.5, lead=1),
        unit("Spearman II",      270,   "Guardsman",  ["Melee"],          315,   lead=1),
        unit("Archer III",       480,   "Guardsman",  ["Ranged"],         315,   lead=1),
        unit("Swordsman III",    480,   "Specialist", ["Melee"],          313.5, lead=1),
        unit("Spearman III",     480,   "Guardsman",  ["Melee"],          315,   lead=1),
        unit("Archer IV",        870,   "Guardsman",  ["Ranged"],         315,   lead=1),
        unit("Swordsman IV",     870,   "Specialist", ["Melee"],          313.5, lead=1),
        unit("Spearman IV",      870,   "Guardsman",  ["Melee"],          315,   lead=1),
        unit("Archer V",         1560,  "Guardsman",  ["Ranged"],         315,   lead=1),
        unit("Spearman V",       1560,  "Guardsman",  ["Melee"],          315,   lead=1),
        unit("Rider II",         540,   "Guardsman",  ["Mounted"],        315,   lead=2),
        unit("Rider III",        960,   "Guardsman",  ["Mounted"],        315,   lead=2),
        unit("Rider IV",         1740,  "Guardsman",  ["Mounted"],        315,   lead=2),
        unit("Rider V",          3150,  "Guardsman",  ["Mounted"],        315,   lead=2),
        unit("Battle Griffin V", 30000, "Guardsman",  ["Flying", "Beast"], 264,  lead=20),
        # S5 unlocked  -- four new Specialist tier-V units, extending
        # Specialist above the previous cap (Swordsman IV). Deadshot V/Lion Rider V/
        # Vultures V are new unit LINES (no II/III/IV predecessors given), not
        # extensions of an existing Guardsman line -- don't conflate them with their
        # same-base-HP Guardsman counterparts (Archer V/Rider V) despite matching HP.
        # Vultures V is the first Specialist+Flying unit in the roster (Battle Griffin
        # V is Guardsman+Flying+Beast, a different, much tankier line -- lead cost 20
        # vs Vultures V's 1).
        unit("Deadshot V",       1560,  "Specialist", ["Ranged"],         0,     lead=1),
        unit("Swordsman V",      1560,  "Specialist", ["Melee"],          0,     lead=1),
        unit("Lion Rider V",     3150,  "Specialist", ["Mounted"],        0,     lead=2),
        unit("Vultures V",       1560,  "Specialist", ["Flying"],         0,     lead=1),
        # G6 unlocked  -- four new Guardsman tier-VI units, extending the
        # Guardsman line above tier V. Like Ballistae VI (E6), the tier-VI names break
        # the I-V lineage: Heavy Arbalester VI continues the Archer line, Heavy
        # Halberdier VI the Spearman line, Mounted Knight VI the Rider line, Battle
        # Griffin VI the Battle Griffin line.
        #   Heavy Arbalester VI (eff 15,016) / Heavy Halberdier VI (eff 14,988) slot
        # into the ordinary infantry chain just below Lion Rider V / Rider V -- no
        # special handling. Mounted Knight VI (eff 30,296) becomes the highest-eff-HP
        # REGULAR infantry type, so it now sets infantry's minimum stack, i.e. M3's
        # ceiling -- still no special handling, alloc_strict places it automatically.
        #   Battle Griffin VI is the structural one: eff HP 284,430 sits ABOVE every M4
        # unit (max 210,630, Ice Phoenix) and BELOW every M5 unit (min 569,940, Fearsome
        # Manticore), so by the same eff-HP ordering rule that puts Battle Griffin V
        # between M3 and M4, Griffin VI belongs between M4 and M5. It is therefore a
        # SECOND Leadership-funded interleave, pulled out of the strict infantry chain
        # by name in run_calculator() exactly like Griffin V -- see the death-order
        # comments there.
        unit("Heavy Arbalester VI", 2820,  "Guardsman", ["Ranged"],          0, lead=1),
        unit("Heavy Halberdier VI", 2820,  "Guardsman", ["Melee"],           0, lead=1),
        unit("Mounted Knight VI",   5700,  "Guardsman", ["Mounted"],         0, lead=2),
        unit("Battle Griffin VI",   57000, "Guardsman", ["Flying", "Beast"], 0, lead=20),
        # tier-VI units. If your account has the Ranged and Melee members of this tier (the
        # Deadshot VI / Swordsman VI equivalents) are NOT yet unlocked -- add them here
        # when you gets them. Base HP matches the Guardsman tier-VI pattern exactly
        # (2,820 for the 1-Lead slots, 5,700 for the 2-Lead Mounted slot).
        #   Name note: you gave "Vulture VI" SINGULAR, whereas the tier-V unit is
        # "Vultures V" PLURAL. Recorded as given -- not a typo to normalise.
        #   Lion Rider VI (eff 30,239) lands just BELOW Mounted Knight VI (eff 30,296):
        # same base HP and same Mounted bucket, but Specialist Health is 85pp vs
        # Guardsman's 86pp, a 1pp gap that puts them 57 eff HP apart. Mounted Knight VI
        # therefore still sets infantry's minimum stack (= M3's ceiling); Lion Rider VI
        # slots directly beneath it as the second-tankiest regular infantry type.
        unit("Vulture VI",          2820,  "Specialist", ["Flying"],         0, lead=1),
        unit("Lion Rider VI",       5700,  "Specialist", ["Mounted"],        0, lead=2),
    ]
    catapults = [
        unit("Catapult III", 4860,  "Engineer", ["Siege Engine"], 772.5, lead=10),
        unit("Catapult IV",  8750,  "Engineer", ["Siege Engine"], 772.5, lead=10),
        unit("Catapult V",   15800, "Engineer", ["Siege Engine"], 772.5, lead=10),
        # Ballistae VI added  -- new top Engineer/Siege Engine tier (E6
        # unlocked). Unconditional baseline like III/IV/V (not gated behind an
        # include_ flag like II/I), since it's now a permanently unlocked tier, not an
        # optional lower-tier test. Different NAME from the Catapult I-V lineage but
        # same Subtype/Combat Class -- pooled together, picked up automatically by
        # find_squad_maximizing_stack's eff-HP-descending catapult_order (becomes the
        # new first tier grown in Phase 2, ahead of Catapult V).
        unit("Ballistae VI", 28400, "Engineer", ["Siege Engine"], 772.5, lead=10),
    ]
    if include_catapult_ii or include_catapult_i:
        catapults.insert(0, unit("Catapult II", 2700, "Engineer", ["Siege Engine"], 772.5, lead=10))
    if include_catapult_i:
        catapults.insert(0, unit("Catapult I", 1500, "Engineer", ["Siege Engine"], 772.5, lead=10))
    if exclude_catapult_names:
        excl = set(exclude_catapult_names)
        catapults = [c for c in catapults if c["name"] not in excl]
    monsters_m3 = [
        unit("Water Elemental", 5700,  "Monster", ["Ranged", "Elemental"], 333, dom=3, tier="M3"),
        unit("Battle Boar",     11700, "Monster", ["Mounted", "Beast"],    333, dom=6, tier="M3"),
        unit("Emerald Dragon",  13500, "Monster", ["Flying", "Dragon"],   282, dom=7, tier="M3"),
        unit("Stone Gargoyle",  15600, "Monster", ["Flying", "Giant"],    282, dom=8, tier="M3"),
    ]
    monsters_m4 = [
        unit("Gorgon Medusa",       36000, "Monster", ["Ranged", "Beast"],    333, dom=10, tier="M4"),
        unit("Many-Armed Guardian", 39000, "Monster", ["Melee", "Giant"],    333, dom=11, tier="M4"),
        unit("Magic Dragon",        45000, "Monster", ["Ranged", "Dragon"],  333, dom=13, tier="M4"),
        unit("Ice Phoenix",         51000, "Monster", ["Flying", "Elemental"], 282, dom=15, tier="M4"),
    ]
    monsters_m5 = [
        unit("Desert Vanquisher",  126000, "Monster", ["Mounted", "Dragon"],    333, dom=20, tier="M5"),
        unit("Flaming Centaur",    132000, "Monster", ["Mounted", "Elemental"], 333, dom=21, tier="M5"),
        unit("Fearsome Manticore", 138000, "Monster", ["Flying", "Beast"],      282, dom=22, tier="M5"),
        unit("Ettin",              144000, "Monster", ["Melee", "Giant"],       333, dom=23, tier="M5"),
    ]
    # M6 unlocked  -- new tier, dies after M5 (ceiling = M5's minimum stack),
    # same unordered-internally treatment as M4/M5.
    monsters_m6 = [
        unit("Crystal Dragon",   360000, "Monster", ["Melee", "Dragon"],    333, dom=33, tier="M6"),
        unit("Ruby Golem",       390000, "Monster", ["Melee", "Elemental"], 333, dom=35, tier="M6"),
        unit("Jungle Destroyer", 390000, "Monster", ["Melee", "Beast"],     333, dom=34, tier="M6"),
        unit("Troll Rider",      330000, "Monster", ["Mounted", "Giant"],   333, dom=30, tier="M6"),
    ]
    mercs_no_emh = [
        unit("Jungle King",    330000,  "Monster", ["Melee", "Beast"],       333,   auth=33),
        # Mounted/Elemental, auth 40), Lightning Lord (460,000, Ranged/Giant, auth 45),
        # Life Dragon (720,000, Flying/Dragon, auth 70), Cursed Dragon (960,000,
        # Flying/Dragon, auth 93). Stats kept here so they can be restored verbatim if
        # Monster-subtype mercs out and new ones in as he acquires them.
        unit("Golden Dragon",  510000,  "Monster", ["Flying", "Dragon"],     282,   auth=50),
        unit("Overlord",       600000,  "Monster", ["Ranged", "Giant"],      333,   auth=60),
        unit("Palintone",      102000,  "Engineer", ["Siege Engine"],       772.5, auth=10),
        unit("Sandworm",       1290000, "Monster", ["Melee", "Elemental"],  333,   auth=128),
        unit("Fire Lord",      1680000, "Monster", ["Ranged", "Elemental"], 333,   auth=164),
        # subtype mercs above -- Guardsman subtype, single combat_class each, same pattern
        # as EMH VII. These get Guardsman Health
        # + the relevant combat_class bucket from PERMANENT_BONUS_RULES, NOT the
        # Beast/Dragon/Elemental/Giant buckets the Monster-subtype mercs above get.
        unit("Superior Epic Monster Hunter", 75000, "Guardsman", [], 0, auth=1),
        # mercs (the pool was previously Monster-subtype or Guardsman-subtype only).
        # They pick up the Specialist Health bucket (85pp) plus their combat_class bucket,
        # NOT Guardsman Health and NOT the Beast/Dragon/Elemental/Giant buckets.
        # Cost pattern 1/1/2/20 mirrors the Arbalester/Legionary/Chariot/Sphynx family.
        # Jago is the outlier: 660,000 base HP (eff ~3.16M) makes it one of the tankiest
        # units in the roster, so only a couple fit under the merc pool's m4_min ceiling.
        unit("Pounder",   33000,  "Specialist", ["Ranged"],  0, auth=1),
        unit("Scarface",  33000,  "Specialist", ["Melee"],   0, auth=1),
        unit("Galloper",  66000,  "Specialist", ["Mounted"], 0, auth=2),
        unit("Jago",      660000, "Specialist", ["Flying"],  0, auth=20),
    ]
    emh = unit("Epic Monster Hunter VII", 11220, "Guardsman", [], 233, auth=1)
    return regular_infantry, catapults, monsters_m3, monsters_m4, monsters_m5, monsters_m6, mercs_no_emh, emh


def sort_key(u):
    return (u["eff_hp"], {"Specialist": 0, "Guardsman": 1}.get(u.get("subtype", ""), 2))


def smooth_fill(alloc, extra_budget, cost_key, ceiling=None):
    """Spread extra_budget across an already-built strict-chain allocation (list of
    {"unit":..., "qty":...} in ascending-eff_hp order), one unit at a time, instead of
    dumping it all into the first entry -- keeps every gap in the chain proportionate."""
    used = [0]

    def try_increment():
        changed = False
        for idx, a in enumerate(alloc):
            cost_i = a["unit"][cost_key]
            if used[0] + cost_i > extra_budget:
                continue
            new_stack = (a["qty"] + 1) * a["unit"]["eff_hp"]
            prev_ceiling = ceiling if idx == 0 else alloc[idx - 1]["qty"] * alloc[idx - 1]["unit"]["eff_hp"]
            if prev_ceiling is None or new_stack < prev_ceiling:
                a["qty"] += 1
                used[0] += cost_i
                changed = True
        return changed

    while try_increment():
        pass
    return used[0]


def alloc_strict(units, cap, cost_key, ceiling=None, floor_target=None, fill_remainder=True):
    us = sorted(units, key=sort_key)
    n = len(us)
    notes = [None] * n
    active = [i for i, u in enumerate(us) if ceiling is None or u["eff_hp"] < ceiling]
    for i in range(n):
        if i not in active:
            notes[i] = "cap violation"
    if not active:
        return [{"unit": us[i], "qty": 0, "note": notes[i]} for i in range(n)], 0
    weights = [us[i][cost_key] / us[i]["eff_hp"] for i in active]
    tw = sum(weights)
    qty = {i: max(1, math.floor(cap * (weights[j] / tw) / us[i][cost_key])) for j, i in enumerate(active)}

    def used():
        return sum(qty[i] * us[i][cost_key] for i in active)

    while used() > cap:
        for i in reversed(active):
            if qty[i] > 1:
                qty[i] -= 1
                break
        else:
            break
    if ceiling is not None and active:
        i0 = active[0]
        mq = math.floor((ceiling - 1) / us[i0]["eff_hp"])
        qty[i0] = min(qty[i0], max(0, mq))
    if floor_target is not None and active:
        i0 = active[0]
        min_q = math.ceil(floor_target / us[i0]["eff_hp"])
        qty[i0] = max(qty[i0], min_q)
        while used() > cap:
            for i in reversed(active):
                if qty[i] > 1:
                    qty[i] -= 1
                    break
            else:
                break
    changed = True
    while changed:
        changed = False
        for j in range(len(active) - 1):
            i, i1 = active[j], active[j + 1]
            sh, sh1 = qty[i] * us[i]["eff_hp"], qty[i1] * us[i1]["eff_hp"]
            if sh1 >= sh:
                nq = max(0, math.floor((sh - 1) / us[i1]["eff_hp"])) if us[i]["eff_hp"] != us[i1]["eff_hp"] else qty[i] - 1
                if nq != qty[i1]:
                    qty[i1] = nq
                    changed = True
    for i in active:
        if qty[i] == 0 and notes[i] is None:
            notes[i] = "order violation"
    i0 = active[0]
    if fill_remainder:
        # Spread leftover cap across the WHOLE chain (one unit at a time, in order,
        # repeating passes) instead of dumping it all into the first unit -- dumping
        # into i0 alone creates an artificially huge gap between it and the next
        # unit while leaving the rest of the chain at its bare minimum. Delegates to
        # smooth_fill() so there's one shared implementation of this logic.
        remaining_budget = cap - used()
        if remaining_budget > 0:
            temp_alloc = [{"unit": us[i], "qty": qty[i]} for i in active]
            smooth_fill(temp_alloc, remaining_budget, cost_key, ceiling=ceiling)
            for idx, i in enumerate(active):
                qty[i] = temp_alloc[idx]["qty"]
    return [{"unit": us[i], "qty": qty.get(i, 0) if notes[i] is None else 0, "note": notes[i]} for i in range(n)], used()


def alloc_unordered(units, cap, cost_key, ceiling):
    result = [{"unit": u, "qty": math.floor((ceiling - 1) / u["eff_hp"]), "note": "unordered"} for u in units]

    def used():
        return sum(a["qty"] * a["unit"][cost_key] for a in result)

    while used() > cap:
        worst = max((a for a in result if a["qty"] > 0), key=lambda a: a["qty"] * a["unit"][cost_key], default=None)
        if worst:
            worst["qty"] -= 1
        else:
            break
    rem = cap - used()
    for a in sorted(result, key=lambda x: x["unit"][cost_key] / x["unit"]["eff_hp"], reverse=True):
        max_q = math.floor((ceiling - 1) / a["unit"]["eff_hp"])
        if rem >= a["unit"][cost_key]:
            extra = min(math.floor(rem / a["unit"][cost_key]), max_q - a["qty"])
            if extra > 0:
                a["qty"] += extra
                rem -= extra * a["unit"][cost_key]
    return result, used()


def min_sh(a):
    s = [x["qty"] * x["unit"]["eff_hp"] for x in a if x["qty"] > 0]
    return min(s) if s else 0


def max_sh(a):
    s = [x["qty"] * x["unit"]["eff_hp"] for x in a if x["qty"] > 0]
    return max(s) if s else 0


def alloc_inverse(units, cap, cost_key):
    n = len(units)
    if cap <= 0 or n == 0:
        return [0] * n, 0
    best_qtys = None
    best_used = 0
    for fq in range(1, cap // units[0][cost_key] + 1):
        qtys = [0] * n
        qtys[0] = fq
        prev_sh = fq * units[0]["eff_hp"]
        for i in range(1, n):
            mq = math.floor((prev_sh - 1) / units[i]["eff_hp"])
            qtys[i] = max(1, mq)
            prev_sh = qtys[i] * units[i]["eff_hp"]
        used = sum(qtys[i] * units[i][cost_key] for i in range(n))
        if used > cap:
            break
        best_qtys = qtys[:]
        best_used = used
    if best_qtys is None:
        best_qtys = [1] * n
        best_used = sum(units[i][cost_key] for i in range(n))
    rem = cap - best_used
    last = units[-1]
    prev_sh = best_qtys[-2] * units[-2]["eff_hp"] if n > 1 else float("inf")
    max_last = math.floor((prev_sh - 1) / last["eff_hp"])
    extra = min(math.floor(rem / last[cost_key]), max_last - best_qtys[-1])
    best_qtys[-1] += max(0, extra)
    best_used += max(0, extra) * last[cost_key]
    return best_qtys, best_used


def run_calculator(leadership, dominance, authority, stack_bonus_pct=0, exclude_names=None, include_catapult_ii=False, include_catapult_i=False, exclude_catapult_names=None):
    r = stack_bonus_pct
    exclude_names = set(exclude_names or [])
    regular_infantry_full, catapults, monsters_m3, monsters_m4, monsters_m5, monsters_m6, mercs_no_emh, emh = build_units(
        r, include_catapult_ii=include_catapult_ii, include_catapult_i=include_catapult_i,
        exclude_catapult_names=exclude_catapult_names
    )

    # Battle Griffin V's effective HP (109,200) is higher than every M3 monster's,
    # so by the "highest effective HP dies last" rule it must die AFTER all of
    # M3 -- even though its Leadership cost is drawn from the same pool as the
    # rest of the infantry. Pull it out of the strict infantry chain and place
    # it as its own link between M3 and M4.
    griffin_unit = next(u for u in regular_infantry_full if u["name"] == "Battle Griffin V")
    # Battle Griffin VI (G6, unlocked ) gets the same treatment one tier
    # further down the chain: its eff HP (284,430) is above every M4 unit's and below
    # every M5 unit's, so it interleaves between M4 and M5. Looked up with a default of
    # None so this still runs against a roster that doesn't have it (e.g. the
    griffin6_unit = next((u for u in regular_infantry_full if u["name"] == "Battle Griffin VI"), None)
    _interleaved = {"Battle Griffin V", "Battle Griffin VI"}
    regular_infantry = [u for u in regular_infantry_full if u["name"] not in _interleaved and u["name"] not in exclude_names]

    # --- Sequence A: Leadership (catapults + infantry, excl. Battle Griffin V) ---
    # Chain is: catapults -> infantry -> M3 -> Palintone (siege exception) ->
    # Battle Griffin V -> M4 -> M5. Each candidate cat_lead is evaluated using
    # the SAME finalization path (Griffin reservation + smoothing) that gets
    # used for real, so the "gap" the search minimizes is the one that actually
    # materializes -- evaluating it any other way (e.g. an unconstrained/
    # unsmoothed infantry estimate) reports a gap that never happens.
    # Reference unit for the search loop's lower-bound heuristic: whichever
    # catapult tier has the lowest effective HP (normally Catapult III, or
    # Catapult II if included) needs the most quantity to clear infantry's max.
    lowest_catapult = min(catapults, key=lambda u: u["eff_hp"])
    # The gap-slotting siege exception. The game offers each account exactly ONE
    # Authority-funded siege-engine mercenary appropriate to its level (Palintone,
    # Trebuchet, and so on at other levels), so it is identified STRUCTURALLY -- the
    # merc carrying the Siege Engine tag -- rather than by name. That means it works
    # on any account without configuration, and keeps working when the game swaps in
    # a different one at a higher level. Returns None if the account has none; every
    # downstream use is guarded for that.
    siege_merc = next((m for m in mercs_no_emh if "Siege Engine" in m["combat_class"]), None)

    def finalize_candidate(cat_lead):
        inf_lead = leadership - cat_lead
        inf_test, _ = alloc_strict(regular_infantry, inf_lead, "lead")
        inf_nat_max = max_sh(inf_test)
        cat_min_qty_est = math.ceil((inf_nat_max + 1) / lowest_catapult["eff_hp"])
        if cat_lead < cat_min_qty_est * lowest_catapult["lead"] + 20:
            return None
        ca, cu = alloc_strict(catapults, cat_lead, "lead", floor_target=inf_nat_max + 1)
        if cu != cat_lead or min_sh(ca) <= inf_nat_max:
            return None
        cat_min = min_sh(ca)

        # Pass 1: estimate Battle Griffin V's Leadership reserve via M3. Palintone no
        # longer factors into Griffin's ceiling (moved  -- see the "Real
        # Palintone" note below for its new position, between catapults and infantry).
        inf_pass1, _ = alloc_strict(regular_infantry, inf_lead, "lead", ceiling=cat_min, fill_remainder=False)
        m3_pass1, m3_used_pass1 = alloc_strict(monsters_m3, dominance, "dom", ceiling=min_sh(inf_pass1))
        m3_min_pass1 = min_sh(m3_pass1)
        target_griffin_qty = max(0, math.floor((m3_min_pass1 - 1) / griffin_unit["eff_hp"])) if m3_min_pass1 else 0
        griffin_reserve = target_griffin_qty * griffin_unit["lead"]

        # Battle Griffin VI sits one tier further down (between M4 and M5), so its own
        # Leadership reserve has to be estimated one cascade step further too: M3 ->
        # Griffin V's stack -> M4 -> Griffin VI's ceiling. Small in absolute terms (20
        # Lead/unit against an M4-floor ceiling, so typically a handful of units), but
        # reserved on the same principle as Griffin V's -- otherwise the infantry chain
        # consumes the Leadership first and Griffin VI never gets fielded.
        griffin6_reserve = 0
        if griffin6_unit is not None and m3_min_pass1:
            g5_stack_pass1 = target_griffin_qty * griffin_unit["eff_hp"]
            m4_ceiling_pass1 = g5_stack_pass1 if g5_stack_pass1 else m3_min_pass1
            m4_pass1, _ = alloc_unordered(monsters_m4, dominance - m3_used_pass1, "dom", ceiling=m4_ceiling_pass1)
            m4_min_pass1 = min_sh(m4_pass1)
            if m4_min_pass1:
                target_griffin6_qty = max(0, math.floor((m4_min_pass1 - 1) / griffin6_unit["eff_hp"]))
                griffin6_reserve = target_griffin6_qty * griffin6_unit["lead"]

        # Pass 2: reserve that Leadership from infantry, get the real base allocation.
        inf_final, infantry_used_base = alloc_strict(
            regular_infantry, inf_lead - griffin_reserve - griffin6_reserve, "lead", ceiling=cat_min, fill_remainder=False
        )
        infantry_min_stack = min_sh(inf_final)

        # Real M3 (must die after all infantry, incl. catapults).
        m3_alloc, m3_used = alloc_strict(monsters_m3, dominance, "dom", ceiling=infantry_min_stack)
        m3_min = min_sh(m3_alloc)
        m3_max_stack = max_sh(m3_alloc)

        # Real Battle Griffin V (dies after M3 -- Palintone no longer sits between M3
        # and Griffin, see the new Palintone positioning note in the outer scope below).
        griffin_ceiling = m3_min
        griffin_lead_budget = inf_lead - infantry_used_base
        griffin_qty = max(0, min(
            griffin_lead_budget // griffin_unit["lead"],
            math.floor((griffin_ceiling - 1) / griffin_unit["eff_hp"]) if griffin_ceiling else 0,
        ))

        leftover_lead = griffin_lead_budget - griffin_qty * griffin_unit["lead"]

        # Real Battle Griffin VI (dies after M4, before M5). Its true ceiling is M4's
        # minimum stack, which is fully determined here -- M4 depends only on m3_used
        # and Griffin V's stack, both already final at this point -- so this reproduces
        # the main body's M4 allocation exactly rather than approximating it. Sized
        # before the main body's M4/M5/M6 growth loop runs, which only ever RAISES M4's
        # minimum stack, so this quantity stays strictly under the final ceiling.
        griffin6_qty = 0
        if griffin6_unit is not None and leftover_lead >= griffin6_unit["lead"]:
            m4_ceiling_here = griffin_qty * griffin_unit["eff_hp"] if griffin_qty > 0 else griffin_ceiling
            if m4_ceiling_here:
                m4_here, _ = alloc_unordered(monsters_m4, dominance - m3_used, "dom", ceiling=m4_ceiling_here)
                m4_min_here = min_sh(m4_here)
                if m4_min_here:
                    griffin6_qty = max(0, min(
                        leftover_lead // griffin6_unit["lead"],
                        math.floor((m4_min_here - 1) / griffin6_unit["eff_hp"]),
                    ))
            leftover_lead -= griffin6_qty * griffin6_unit["lead"]

        # Spread whatever neither Griffin needed across the WHOLE infantry chain
        # (not dumped entirely into Swordsman III) so every gap stays proportionate.
        if leftover_lead > 0:
            smooth_fill(inf_final, leftover_lead, "lead", ceiling=cat_min)

        inf_max = max_sh(inf_final)
        if cat_min <= inf_max:
            return None
        return {
            "gap": cat_min - inf_max, "cat_lead": cat_lead, "ca": ca, "inf_final": inf_final,
            "cat_min": cat_min, "inf_max": inf_max, "m3_alloc": m3_alloc, "m3_used": m3_used,
            "m3_min": m3_min, "m3_max_stack": m3_max_stack,
            "griffin_qty": griffin_qty, "griffin_ceiling": griffin_ceiling,
            "griffin6_qty": griffin6_qty,
        }

    best = None
    for cat_lead in range(30, leadership, 10):
        result = finalize_candidate(cat_lead)
        if result is None:
            continue
        if best is None or result["gap"] < best["gap"]:
            best = result
        if best and cat_lead > best["cat_lead"] + 500:
            break

    if best is None:
        raise RuntimeError("No valid Leadership allocation found — cap may be too small for a catapult+infantry split.")

    best_cat_lead = best["cat_lead"]
    best_cat_alloc = best["ca"]
    inf_final = best["inf_final"]
    cat_min = best["cat_min"]
    inf_max = best["inf_max"]
    m3_alloc, m3_used = best["m3_alloc"], best["m3_used"]
    m3_min, m3_max_stack = best["m3_min"], best["m3_max_stack"]
    griffin_qty = best["griffin_qty"]
    griffin_stack = griffin_qty * griffin_unit["eff_hp"]
    griffin_ceiling = best["griffin_ceiling"]
    griffin6_qty = best["griffin6_qty"]
    griffin6_stack = griffin6_qty * griffin6_unit["eff_hp"] if griffin6_unit else 0

    # EMH: eff HP (37,363ish) is lower than most of M3, so per the health order
    # it dies inside M3, between Water Elemental and Battle Boar. Pure
    # side-insertion funded by Authority -- doesn't touch Dominance/Leadership.
    emh_qty = 0
    if authority > 0 and m3_max_stack:
        emh_qty = max(0, min(authority // emh["auth"], math.floor((m3_max_stack - 1) / emh["eff_hp"])))
    emh_stack = emh_qty * emh["eff_hp"]
    auth_after_emh = authority - emh_qty * emh["auth"]

    # the gap between the highest-health catapult (cat_min, the last catapult to die)
    # and the first Leadership infantry unit (inf_max, the first infantry type to
    # die) -- i.e. Palintone is now a THIRD forced-early exception extending the
    # catapults' "cannon fodder dies first" block, using the same HP/strength-mismatch
    # logic already documented for catapults. This reuses the "known trade-off" gap
    # sat empty. Maximize Palintone's quantity just under cat_min, but ONLY if that
    # quantity's stack still clears inf_max -- if Palintone's own eff_hp is too large
    # relative to the gap (or the Authority budget can't afford enough units) to find
    # ANY quantity that lands strictly between inf_max and cat_min, Palintone is not
    # fielded at all (qty=0) rather than being force-fit somewhere incorrect (e.g.
    # inside the infantry chain). This is a real possible outcome, not a bug --
    # smaller gaps or larger one-off bonuses on Siege Engine/Engineer health make it
    # more likely to happen.
    siege_merc_qty = 0
    if siege_merc and authority > 0 and cat_min > inf_max:
        max_under_ceiling = math.floor((cat_min - 1) / siege_merc["eff_hp"])
        budget_max = auth_after_emh // siege_merc["auth"]
        candidate_qty = min(max_under_ceiling, budget_max)
        if candidate_qty > 0 and candidate_qty * siege_merc["eff_hp"] > inf_max:
            siege_merc_qty = candidate_qty
    siege_merc_stack = siege_merc_qty * siege_merc["eff_hp"] if siege_merc else 0
    auth_remaining = auth_after_emh - (siege_merc_qty * siege_merc["auth"] if siege_merc else 0)

    # --- Sequence B steps 2-5: M4 (ceiling = Battle Griffin V's stack), Battle Griffin VI
    # (ceiling = M4 min, added ), M5 (ceiling = Griffin VI's stack), M6
    # (ceiling = M5 min, unlocked ) ---
    m4_ceiling = griffin_stack if griffin_qty > 0 else griffin_ceiling
    m4_alloc, m4_used = alloc_unordered(monsters_m4, dominance - m3_used, "dom", ceiling=m4_ceiling)
    m4_min = min_sh(m4_alloc)
    # Griffin VI's quantity was fixed in finalize_candidate (it had to be, so its
    # Leadership could be withheld from the infantry smoothing there) -- the M4
    # allocation it was sized against is the identical call above, same inputs.
    # If it isn't fielded (qty 0: no Griffin VI in the roster, or M4's floor is below
    # even one unit's 284,430 eff HP, or no Leadership left), M5 falls back to M4's
    # minimum stack exactly as before -- same graceful no-field behavior as Palintone.
    m5_ceiling = griffin6_stack if griffin6_qty > 0 else m4_min
    m5_alloc, m5_used = alloc_unordered(monsters_m5, dominance - m3_used - m4_used, "dom", ceiling=m5_ceiling)
    m5_min = min_sh(m5_alloc)
    m6_alloc, m6_used = alloc_unordered(monsters_m6, dominance - m3_used - m4_used - m5_used, "dom", ceiling=m5_min)
    dom_used = m3_used + m4_used + m5_used + m6_used

    lead_used = (best_cat_lead + sum(a["qty"] * a["unit"]["lead"] for a in inf_final)
                 + griffin_qty * griffin_unit["lead"]
                 + (griffin6_qty * griffin6_unit["lead"] if griffin6_unit else 0))

    seq_a = []
    for a in best_cat_alloc + inf_final:
        if a["qty"] > 0:
            seq_a.append((a["unit"]["name"], a["qty"], a["unit"]["base_hp"], a["unit"]["eff_hp"], a["qty"] * a["unit"]["eff_hp"]))
    if griffin_qty > 0:
        seq_a.append((griffin_unit["name"], griffin_qty, griffin_unit["base_hp"], griffin_unit["eff_hp"], griffin_stack))
    if griffin6_qty > 0:
        seq_a.append((griffin6_unit["name"], griffin6_qty, griffin6_unit["base_hp"], griffin6_unit["eff_hp"], griffin6_stack))
    seq_a.sort(key=lambda x: x[4], reverse=True)

    m5_min_sh = min_sh(m5_alloc)
    changed = True
    while changed:
        changed = False
        for a in m6_alloc:
            if dominance - dom_used >= a["unit"]["dom"] and (a["qty"] + 1) * a["unit"]["eff_hp"] < m5_min_sh:
                a["qty"] += 1
                dom_used += a["unit"]["dom"]
                changed = True
        for a in m5_alloc:
            if dominance - dom_used >= a["unit"]["dom"] and (a["qty"] + 1) * a["unit"]["eff_hp"] < m5_ceiling:
                a["qty"] += 1
                dom_used += a["unit"]["dom"]
                changed = True
        for a in m4_alloc:
            if dominance - dom_used >= a["unit"]["dom"] and (a["qty"] + 1) * a["unit"]["eff_hp"] < m4_ceiling:
                a["qty"] += 1
                dom_used += a["unit"]["dom"]
                changed = True
    m4_min = min_sh(m4_alloc)

    seq_b = [(a["unit"]["name"], a["qty"], a["unit"]["base_hp"], a["unit"]["eff_hp"], a["qty"] * a["unit"]["eff_hp"], a["unit"]["tier"])
              for a in m3_alloc + m4_alloc + m5_alloc + m6_alloc if a["qty"] > 0]

    # --- Sequence C: Authority ---
    # EMH and Palintone are exceptions already placed above (inside/after M3).
    # Everyone else (Jungle King .. Fire Lord) only needs to die after M4 (not
    # strictly after M5, and not strictly ordered against each other) -- a
    # strict chain collapses because these mercs' own effective HP is close to
    # or exceeds M5's ceiling, leaving no room for 8+ distinct decreasing
    # levels. Treat them like the M4/M5 "unordered" tiers instead.
    # Exclude the gap-slotting siege merc by IDENTITY, not by name -- it is placed
    # separately above, so leaving it here would field it twice on any account whose
    # siege merc is called something other than Palintone.
    final_mercs = [m for m in mercs_no_emh if m is not siege_merc]
    big_merc_alloc, big_merc_used = ([], 0)
    if authority > 0 and auth_remaining > 0 and m4_min:
        big_merc_alloc, big_merc_used = alloc_unordered(final_mercs, auth_remaining, "auth", ceiling=m4_min)

    auth_used = (emh_qty * emh["auth"]
                 + (siege_merc_qty * siege_merc["auth"] if siege_merc else 0)
                 + big_merc_used)

    seq_c = []
    if emh_qty > 0:
        seq_c.append((emh["name"], emh_qty, emh["base_hp"], emh["eff_hp"], emh_stack))
    if siege_merc_qty > 0:
        seq_c.append((siege_merc["name"], siege_merc_qty, siege_merc["base_hp"], siege_merc["eff_hp"], siege_merc_stack))
    for a in big_merc_alloc:
        if a["qty"] > 0:
            seq_c.append((a["unit"]["name"], a["qty"], a["unit"]["base_hp"], a["unit"]["eff_hp"], a["qty"] * a["unit"]["eff_hp"]))
    seq_c.sort(key=lambda x: x[4], reverse=True)

    return {
        "leadership": {"cap": leadership, "used": lead_used, "stacks": seq_a},
        "dominance": {"cap": dominance, "used": dom_used, "stacks": seq_b},
        "authority": {"cap": authority, "used": auth_used, "stacks": seq_c},
    }


def print_report(result):
    lead, dom, auth = result["leadership"], result["dominance"], result["authority"]

    print("=== LEADERSHIP ===")
    for name, qty, base_hp, eff_hp, stack_hp in lead["stacks"]:
        print(f"{name:22s} qty={qty:>8,}  unit_health={base_hp:>10,}  eff_hp/unit={eff_hp:>10,}  stack_hp={stack_hp:>16,.1f}")
    pct = 100 * lead["used"] / lead["cap"] if lead["cap"] else 0
    print(f"Leadership used: {lead['used']:,}/{lead['cap']:,} ({pct:.1f}%)")

    print("\n=== DOMINANCE ===")
    for name, qty, base_hp, eff_hp, stack_hp, tier in dom["stacks"]:
        print(f"{name:22s} qty={qty:>8,}  unit_health={base_hp:>10,}  eff_hp/unit={eff_hp:>10,}  stack_hp={stack_hp:>16,.1f}  [{tier}]")
    pct = 100 * dom["used"] / dom["cap"] if dom["cap"] else 0
    print(f"Dominance used: {dom['used']:,}/{dom['cap']:,} ({pct:.1f}%)")

    print("\n=== AUTHORITY ===")
    if auth["cap"] == 0:
        print("(skipped - cap is 0)")
    else:
        for name, qty, base_hp, eff_hp, stack_hp in auth["stacks"]:
            print(f"{name:22s} qty={qty:>8,}  unit_health={base_hp:>10,}  eff_hp/unit={eff_hp:>10,}  stack_hp={stack_hp:>16,.1f}")
        pct = 100 * auth["used"] / auth["cap"] if auth["cap"] else 0
        print(f"Authority used: {auth['used']:,}/{auth['cap']:,} ({pct:.1f}%)")


def combined_death_order(result):
    """Merge Leadership/Dominance/Authority stacks into one list, sorted by stack HP
    descending (dies first -> dies last). Each entry: (name, pool, qty, base_hp, eff_hp, stack_hp)."""
    combined = []
    for name, qty, base_hp, eff_hp, stack_hp in result["leadership"]["stacks"]:
        combined.append((name, "Leadership", qty, base_hp, eff_hp, stack_hp))
    for name, qty, base_hp, eff_hp, stack_hp, tier in result["dominance"]["stacks"]:
        combined.append((name, f"Dominance/{tier}", qty, base_hp, eff_hp, stack_hp))
    for name, qty, base_hp, eff_hp, stack_hp in result["authority"]["stacks"]:
        combined.append((name, "Authority", qty, base_hp, eff_hp, stack_hp))
    combined.sort(key=lambda x: x[5], reverse=True)
    return combined


def print_full_death_order(result):
    combined = combined_death_order(result)
    print("=== FULL DEATH ORDER (dies first -> dies last) ===")
    prev_stack_hp = None
    for i, (name, pool, qty, base_hp, eff_hp, stack_hp) in enumerate(combined, 1):
        flag = " *** VIOLATION (>= previous) ***" if prev_stack_hp is not None and stack_hp >= prev_stack_hp else ""
        print(f"{i:>2}. {name:22s} [{pool:15s}] qty={qty:>8,}  unit_health={base_hp:>10,}  eff_hp/unit={eff_hp:>10,}  stack_hp={stack_hp:>16,.1f}{flag}")
        prev_stack_hp = stack_hp


def build_cost_lookup(r=0, include_catapult_ii=False, include_catapult_i=False):
    """name -> per-unit cap cost (Leadership/Dominance/Authority, whichever pool
    the unit belongs to), for recovery-cost accounting."""
    regular_infantry, catapults, monsters_m3, monsters_m4, monsters_m5, monsters_m6, mercs_no_emh, emh = build_units(
        r, include_catapult_ii=include_catapult_ii, include_catapult_i=include_catapult_i
    )
    lookup = {}
    for u in regular_infantry + catapults:
        lookup[u["name"]] = u["lead"]
    for u in monsters_m3 + monsters_m4 + monsters_m5 + monsters_m6:
        lookup[u["name"]] = u["dom"]
    for u in mercs_no_emh + [emh]:
        lookup[u["name"]] = u["auth"]
    return lookup


GOLD_RECOVERY_MULTIPLIER = {"Leadership": 4, "Dominance": 16, "Authority": 8}
GOLD_RECOVERY_REDUCTION = 4.34
# ^^ REPLACE THIS WITH YOUR OWN VALUE. The raw
# "qty * cap_cost * pool_multiplier" figure overstates real gold recovery cost,
# and this divisor corrects it. It is ACCOUNT-SPECIFIC: it scales with your
# Temple level, so it rises as you upgrade and it will differ between players.
#
# To find yours: note the gold cost the game quotes to revive a stack you
# actually lost, then solve  raw / observed  for the divisor. Do it on two or
# three different unit types to confirm you get a consistent number.
#
# Applied PER STACK -- each unit type's raw cost is divided and rounded up on
# its own, then summed. NOT applied once to a grand total.


def recovery_cost_first_n(result, cost_lookup, n=4):
    """Gold recovery cost of the first n stacks to die -- for each stack, raw = qty *
    unit's own cap cost * that pool's gold multiplier, then contribution =
    ceil(raw / GOLD_RECOVERY_REDUCTION), summed across the first n stacks -- the cost
    of a short engagement (e.g. a 'k-squad' enemy that gets k hits, each wiping one
    stack entirely). Gold multiplier by pool : Leadership x4,
    Dominance x16, Authority x8 -- these are NOT interchangeable 1:1, so the multiplier
    must be applied per-stack by its own pool rather than summing raw cap-cost units
    across pools. The GOLD_RECOVERY_REDUCTION divisor  is also
    applied per-stack, each stack's contribution rounded up independently -- see
    GOLD_RECOVERY_REDUCTION's own comment for why per-stack, not per-total."""
    combined = combined_death_order(result)
    total = 0
    breakdown = []
    for name, pool, qty, base_hp, eff_hp, stack_hp in combined[:n]:
        cost = cost_lookup.get(name)
        multiplier = GOLD_RECOVERY_MULTIPLIER[pool.split("/")[0]]
        if cost is not None:
            raw = qty * cost * multiplier
            contribution = math.ceil(raw / GOLD_RECOVERY_REDUCTION)
        else:
            contribution = 0
        total += contribution
        breakdown.append((name, pool, qty, cost, multiplier, contribution))
    return total, breakdown


def full_recovery_cost(result, cost_lookup):
    """Total gold to recover EVERY stack in the army, per pool -- not just the first N to
    die. Added  at your request; this is the headline recovery metric now,
    with recovery_cost_first_n() retained alongside it for the limited-hit view.

    Same arithmetic as recovery_cost_first_n: raw = qty * unit's own cap cost * that pool's
    gold multiplier, divided by GOLD_RECOVERY_REDUCTION and rounded up PER STACK, then
    summed. Returns {"Leadership": n, "Dominance": n, "Authority": n, "total": n,
    "lead_plus_dom": n}."""
    out = {}
    for pool, key in (("Leadership", "leadership"), ("Dominance", "dominance"),
                      ("Authority", "authority")):
        s = 0
        for row in result[key]["stacks"]:
            name, qty = row[0], row[1]
            cost = cost_lookup.get(name)
            if cost is None:
                continue
            s += math.ceil(qty * cost * GOLD_RECOVERY_MULTIPLIER[pool] / GOLD_RECOVERY_REDUCTION)
        out[pool] = s
    out["lead_plus_dom"] = out["Leadership"] + out["Dominance"]
    out["total"] = out["lead_plus_dom"] + out["Authority"]
    return out


def find_settled_exclusion_depth(leadership, dominance, authority, stack_bonus_pct=0,
                                  include_catapult_ii=False, include_catapult_i=False,
                                  exclude_catapult_names=None,
                                  dom_threshold_pct=99.5):
    """Sweep exclusion depth (removing the lowest-effective-HP Leadership infantry
    types one at a time), find the first depth where Dominance usage is
    'statistically ~100%' (>= dom_threshold_pct), then back up one depth from
    there -- this is the confirmed settled-depth rule (see the README)."""
    regular_infantry_full, *_ = build_units(stack_bonus_pct)
    # Both Griffins are excluded from the sweep pool: run_calculator pulls them out of
    # the strict infantry chain by name (they interleave at M3->M4 and M4->M5), so
    # naming either in exclude_names would have no effect anyway.
    infantry_no_griffin = [u for u in regular_infantry_full
                           if u["name"] not in ("Battle Griffin V", "Battle Griffin VI")]
    names_ascending = [u["name"] for u in sorted(infantry_no_griffin, key=sort_key)]

    sweep = []
    peak_depth = None
    for depth in range(0, len(names_ascending)):
        excluded = names_ascending[:depth]
        try:
            res = run_calculator(leadership, dominance, authority, stack_bonus_pct,
                                  exclude_names=excluded, include_catapult_ii=include_catapult_ii,
                                  include_catapult_i=include_catapult_i,
                                  exclude_catapult_names=exclude_catapult_names)
        except RuntimeError:
            break
        dom_pct = 100 * res["dominance"]["used"] / res["dominance"]["cap"] if res["dominance"]["cap"] else 100
        sweep.append((depth, excluded, dom_pct, res))
        if peak_depth is None and dom_pct >= dom_threshold_pct:
            peak_depth = depth
        if peak_depth is not None and depth > peak_depth + 2:
            break

    if peak_depth is None:
        peak_depth = max(sweep, key=lambda x: x[2])[0] if sweep else 0

    settled_depth = max(0, peak_depth - 1)
    settled_excluded = names_ascending[:settled_depth]
    return settled_depth, settled_excluded, sweep


def compare_catapult_configs(leadership, dominance, authority, stack_bonus_pct=0,
                              configs=None, recovery_n=4):
    """For each candidate catapult-tier configuration, find its own settled
    exclusion depth (see find_settled_exclusion_depth), run the calculator, and
    compute the gold recovery cost of the first `recovery_n` stacks to die.
    Returns all results sorted by recovery cost ascending (best first) so the
    cheapest configuration to actually get hit is obvious."""
    if configs is None:
        configs = [
            {"label": "Baseline (Catapult III/IV/V + Ballistae VI)", "include_catapult_ii": False, "include_catapult_i": False},
            {"label": "+ Catapult II", "include_catapult_ii": True, "include_catapult_i": False},
            {"label": "+ Catapult I and II", "include_catapult_ii": True, "include_catapult_i": True},
        ]

    results = []
    for cfg in configs:
        exclude_catapult_names = cfg.get("exclude_catapult_names")
        depth, excluded, sweep = find_settled_exclusion_depth(
            leadership, dominance, authority, stack_bonus_pct,
            include_catapult_ii=cfg["include_catapult_ii"], include_catapult_i=cfg["include_catapult_i"],
            exclude_catapult_names=exclude_catapult_names,
        )
        res = run_calculator(leadership, dominance, authority, stack_bonus_pct, exclude_names=excluded,
                              include_catapult_ii=cfg["include_catapult_ii"], include_catapult_i=cfg["include_catapult_i"],
                              exclude_catapult_names=exclude_catapult_names)
        cost_lookup = build_cost_lookup(stack_bonus_pct, cfg["include_catapult_ii"], cfg["include_catapult_i"])
        recovery_cost, breakdown = recovery_cost_first_n(res, cost_lookup, n=recovery_n)
        results.append({
            "label": cfg["label"], "depth": depth, "excluded": excluded, "result": res,
            "recovery_cost": recovery_cost, "recovery_breakdown": breakdown,
        })

    results.sort(key=lambda r: r["recovery_cost"])
    return results


def print_catapult_config_comparison(comparison):
    print(f"=== CATAPULT CONFIG COMPARISON (gold recovery cost of first-N deaths) ===")
    for r in comparison:
        print(f"\n########## {r['label']}  (settled exclusion depth {r['depth']}: {', '.join(r['excluded']) if r['excluded'] else '(none)'}) ##########")
        print_report(r["result"])
        print()
        print_full_death_order(r["result"])
        print(f"\n  Recovery cost (gold, first {len(r['recovery_breakdown'])} deaths): {r['recovery_cost']:,}")
        for name, pool, qty, cost, multiplier, contribution in r["recovery_breakdown"]:
            print(f"    {name:22s} [{pool:15s}] qty={qty:>6,}  unit_cost={cost}  x{multiplier} gold  contribution={contribution:,}")
    best = comparison[0]
    print(f"\n>>> BEST: {best['label']} (recovery cost {best['recovery_cost']:,} gold)")


def find_squad_maximizing_stack(leadership, dominance, authority, stack_bonus_pct, squad_count=4,
                                 dom_threshold_pct=99.5, recovery_n=None):
    """Alternative to compare_catapult_configs(): instead of picking a catapult config by
    lowest gold recovery cost, greedily MAXIMIZE the number of distinct Leadership-pool
    squads (infantry types + catapult tiers) while keeping Dominance saturated -- confirmed
    workflow . squad_count defaults to 4 (your confirmed standing default epic
    monster squad count -- override when a specific target has a different squad count).
    Rationale (your): more squads means a limited-hit enemy (a squad_count-squad epic
    monster) reaches deeper into cheap/expendable stacks before reaching the genuinely
    strong units at the back of the chain, which then survive to counter-attack for longer.
    This is a different objective than recovery cost, not a replacement for it -- the two
    usually point the same direction (more/thinner stacks
    tend to cost less to lose too) but aren't guaranteed to agree.

    Battle Griffin V is always in the roster from the start , and
    so is Battle Griffin VI  -- squad_count only counts the
    regular infantry types added below them, neither Griffin is a squad candidate.

    Phase 1 -- infantry: start with the `squad_count` highest-eff-HP regular infantry
    TYPES (ties, e.g. Archer V / Spearman V at identical eff_hp under symmetric Ranged/
    Melee bonuses, are always added together as one step, never split -- so the actual
    starting count can slightly exceed squad_count when the count lands mid-tie). Add the
    next-highest remaining type (or tied group) one step at a time while Dominance still
    fills to >= dom_threshold_pct; stop and revert to the last successful roster at the
    first failure. If squad_count itself does NOT fill from the start  -- work BACKWARDS instead,
    dropping the most-recently-added group one at a time until a smaller roster clears the
    threshold, per your fix. Either direction, this phase STILL auto-stops on a threshold
    (unlike phase 2 below) -- you hasn't flagged this phase's stopping rule itself as
    wrong, only the "nowhere to grow" edge case, so the threshold mechanism is untouched.
    Uses a lightweight standalone calculation (infantry -> M3 -> M4 -> M5 via
    alloc_strict/alloc_unordered directly), NOT run_calculator, because run_calculator
    cannot run with zero catapults (its Leadership-split search does min() over the
    catapult pool, which crashes on an empty list -- same class of gap as excluding every
    infantry type). This phase therefore approximates Battle Griffin's own Leadership draw
    as negligible while deciding which infantry types to include -- a real simplification,
    but the final reported numbers come from phase 2's exact run_calculator, not this
    approximation.

    Phase 2 -- catapults . Grows catapult tiers highest-eff-HP first
    (Ballistae VI, then V, then IV, then III, then II, then I -- VI added ) ALL
    THE WAY through every tier, using the REAL
    run_calculator at each step (so Battle Griffin, Palintone, M3/M4/M5, and EMH are all
    handled exactly, not approximated) with the infantry roster held fixed via
    exclude_names. Records every step's full result, Dominance %, and (if recovery_n given)
    gold recovery cost -- you picks the stopping point from the full trajectory, this
    function does not pick one for him. Catapults remain forced to the top of the death
    order exactly as in run_calculator -- only WHICH tiers are in the pool is decided by
    this search, not the death-order mechanic itself.

    Returns {"infantry_included": [...], "infantry_excluded": [...],
    "catapult_trajectory": [{"catapults_included": [...], "dom_pct": ..., "result": ...,
    "recovery_cost": ... or None}, ...]} -- one entry per catapult tier count from 1 to 6
    (was 1 to 5 before Ballistae VI, ), highest-eff-HP-first order. Print any
    entry's "result" with
    print_report()/print_full_death_order() directly."""
    regular_infantry_full, catapults_full, monsters_m3, monsters_m4, monsters_m5, monsters_m6, mercs_no_emh, emh = build_units(
        stack_bonus_pct, include_catapult_ii=True, include_catapult_i=True
    )
    # Neither Griffin is a squad-count candidate -- run_calculator always pulls both out
    # of the infantry chain by name and places them at their own interleave points, so
    # listing them in exclude_names would be silently ignored.
    infantry_no_griffin = [u for u in regular_infantry_full
                           if u["name"] not in ("Battle Griffin V", "Battle Griffin VI")]

    by_eff = {}
    for u in infantry_no_griffin:
        by_eff.setdefault(u["eff_hp"], []).append(u["name"])
    groups_desc = [by_eff[k] for k in sorted(by_eff, reverse=True)]

    def phase1_dom_pct(names):
        pool = [u for u in infantry_no_griffin if u["name"] in names]
        if not pool:
            return 0
        inf_alloc, _ = alloc_strict(pool, leadership, "lead")
        inf_min = min_sh(inf_alloc)
        if not inf_min:
            return 0
        m3_alloc, m3_used = alloc_strict(monsters_m3, dominance, "dom", ceiling=inf_min)
        m3_min = min_sh(m3_alloc)
        m4_alloc, m4_used = alloc_unordered(monsters_m4, dominance - m3_used, "dom", ceiling=m3_min) if m3_min else ([], 0)
        m4_min = min_sh(m4_alloc)
        m5_alloc, m5_used = alloc_unordered(monsters_m5, dominance - m3_used - m4_used, "dom", ceiling=m4_min) if m4_min else ([], 0)
        m5_min = min_sh(m5_alloc)
        m6_alloc, m6_used = alloc_unordered(monsters_m6, dominance - m3_used - m4_used - m5_used, "dom", ceiling=m5_min) if m5_min else ([], 0)
        dom_used = m3_used + m4_used + m5_used + m6_used
        return 100 * dom_used / dominance if dominance else 100

    def flatten(groups):
        out = []
        for g in groups:
            out.extend(g)
        return out

    included_groups = []
    gi = 0
    total = 0
    while gi < len(groups_desc) and total < squad_count:
        included_groups.append(groups_desc[gi])
        total += len(groups_desc[gi])
        gi += 1
    included = flatten(included_groups)

    if phase1_dom_pct(included) >= dom_threshold_pct:
        while gi < len(groups_desc):
            candidate_groups = included_groups + [groups_desc[gi]]
            candidate = flatten(candidate_groups)
            if phase1_dom_pct(candidate) < dom_threshold_pct:
                break
            included_groups = candidate_groups
            included = candidate
            gi += 1
    else:
        # forces the entire roster in immediately, with nowhere to grow) -- work backwards
        # "start narrow, only ever grow" approach starts already past the peak.
        while included_groups and phase1_dom_pct(flatten(included_groups)) < dom_threshold_pct:
            included_groups = included_groups[:-1]
        included = flatten(included_groups)
        if not included_groups:
            raise RuntimeError(
                "Not even the single highest-eff-HP infantry type keeps Dominance filled -- "
                "cap set may be too small for any valid roster."
            )

    infantry_excluded = [u["name"] for u in infantry_no_griffin if u["name"] not in included]

    catapult_order = [u["name"] for u in sorted(catapults_full, key=lambda u: u["eff_hp"], reverse=True)]
    cost_lookup = build_cost_lookup(stack_bonus_pct, True, True) if recovery_n else None
    trajectory = []
    remaining = list(catapult_order)

    for name in catapult_order:
        remaining = [n for n in remaining if n != name]
        res = run_calculator(leadership, dominance, authority, stack_bonus_pct,
                              exclude_names=infantry_excluded, include_catapult_ii=True,
                              include_catapult_i=True, exclude_catapult_names=remaining)
        pct = 100 * res["dominance"]["used"] / res["dominance"]["cap"] if res["dominance"]["cap"] else 100
        entry = {
            "catapults_included": [n for n in catapult_order if n not in remaining],
            "dom_pct": pct, "result": res,
        }
        if cost_lookup is None:
            cost_lookup = build_cost_lookup(stack_bonus_pct, True, True)
        entry["full_recovery"] = full_recovery_cost(res, cost_lookup)
        if cost_lookup is None:
            cost_lookup = build_cost_lookup(stack_bonus_pct, True, True)
        entry["full_recovery"] = full_recovery_cost(res, cost_lookup)
        if recovery_n:
            cost, _ = recovery_cost_first_n(res, cost_lookup, n=recovery_n)
            entry["recovery_cost"] = cost
        trajectory.append(entry)

    return {
        "infantry_included": included, "infantry_excluded": infantry_excluded,
        "catapult_trajectory": trajectory,
    }


def refit_trajectory(leadership, dominance, authority, stack_bonus_pct,
                      dom_threshold_pct=99.5, tolerance_pct=95.0, recovery_n=None):
    """Phase-2 replacement added  (your design). See the README
    "Roster re-fitting" for the full rationale.

    THE PROBLEM IT FIXES: the old Phase 2 froze the infantry roster chosen by Phase 1,
    which had picked it under a NO-CATAPULT approximation. Adding catapults then eats
    15-20%% of Leadership, which lowers every infantry stack, which lowers M3's ceiling,
    which cascades all the way down -- so a roster that filled Dominance in Phase 1 no
    longer did once the catapults were real. Confirmed : a cap set reporting
    84.3%% Dominance actually had 100%% available at a different roster depth.

    WHY NOT EXCLUDE MONSTERS INSTEAD (your first proposal, tested and rejected):
    Dominance is CEILING-bound, not budget-bound -- every tier stops because the cascade
    ceiling blocks it, not because the pool ran dry. Dropping a monster removes a way to
    SPEND Dominance without raising any ceiling, so usage only falls. Measured:
    84.3%% -> 73.3%% -> 62.4%% -> 53.4%% as monsters were dropped lowest-eff-HP-first.
    Excluding cheap INFANTRY is the opposite: it raises the whole chain and lifts every
    ceiling below it. That is why the sweep is over infantry, not monsters.

    For each catapult-tier count, sweep the infantry exclusion depth and pick by your
    rule: take the LARGEST roster (fewest exclusions = most squads) that still reaches
    dom_threshold_pct, then look at ONE MORE squad beyond it and take that instead if it
    still lands within tolerance_pct. Configs that never saturate are KEPT and flagged
    rather than silently dropped -- see the no-silent-caps rule in the README.
    """
    regular_infantry_full, catapults_full, *_ = build_units(
        stack_bonus_pct, include_catapult_ii=True, include_catapult_i=True)
    infantry_no_griffin = [u for u in regular_infantry_full
                           if u["name"] not in ("Battle Griffin V", "Battle Griffin VI")]
    names_ascending = [u["name"] for u in sorted(infantry_no_griffin, key=sort_key)]
    catapult_order = [u["name"] for u in sorted(catapults_full, key=lambda u: u["eff_hp"], reverse=True)]
    cost_lookup = build_cost_lookup(stack_bonus_pct, True, True) if recovery_n else None

    trajectory = []
    remaining = list(catapult_order)
    for name in catapult_order:
        remaining = [n for n in remaining if n != name]
        sweep = {}
        # stop 2 short of emptying the pool -- an empty infantry pool makes the allocator
        # return garbage (negative Dominance) rather than raising, a known unguarded gap
        for depth in range(0, max(1, len(names_ascending) - 2)):
            try:
                res = run_calculator(leadership, dominance, authority, stack_bonus_pct,
                                      exclude_names=names_ascending[:depth],
                                      include_catapult_ii=True, include_catapult_i=True,
                                      exclude_catapult_names=remaining)
            except RuntimeError:
                break
            cap = res["dominance"]["cap"]
            pct = 100 * res["dominance"]["used"] / cap if cap else 100
            if pct < 0 or pct > 100.5:
                break                       # garbage guard
            sweep[depth] = (pct, res)
        if not sweep:
            continue
        hits = [d for d in sorted(sweep) if sweep[d][0] >= dom_threshold_pct]
        if hits:
            pick = min(hits)                # largest roster still saturating
            rule = "saturated"
            cand = pick - 1                 # one MORE squad
            if cand in sweep and sweep[cand][0] >= tolerance_pct:
                pick, rule = cand, "+1 squad (within tolerance)"
        else:
            pick = max(sweep, key=lambda d: sweep[d][0])
            rule = "NEVER SATURATES (best available)"
        pct, res = sweep[pick]
        entry = {
            "catapults_included": [n for n in catapult_order if n not in remaining],
            "dom_pct": pct, "result": res, "exclusion_depth": pick, "rule": rule,
            "infantry_excluded": names_ascending[:pick],
            "infantry_included": [n for n in names_ascending[pick:]],
        }
        if cost_lookup is None:
            cost_lookup = build_cost_lookup(stack_bonus_pct, True, True)
        entry["full_recovery"] = full_recovery_cost(res, cost_lookup)
        if recovery_n:
            cost, _ = recovery_cost_first_n(res, cost_lookup, n=recovery_n)
            entry["recovery_cost"] = cost
        trajectory.append(entry)
    return {"refit": True, "catapult_trajectory": trajectory}


def print_squad_trajectory(out):
    if out.get("refit"):
        # differs per row, so it is printed per row instead of once at the top.
        print(f"{'Catapult tiers':42s} {'Squads':>7s} {'Dominance %':>12s} "
              f"{'FULL L+D':>12s} {'first-N':>10s}  Rule")
        for entry in out["catapult_trajectory"]:
            sq = len(entry["result"]["leadership"]["stacks"])
            cost = f"{entry['recovery_cost']:,}" if "recovery_cost" in entry else "-"
            fr = entry["full_recovery"]["lead_plus_dom"]
            print(f"{', '.join(entry['catapults_included']):42s} {sq:>7d} {entry['dom_pct']:>11.1f}% "
                  f"{fr:>12,} {cost:>10s}  {entry['rule']}")
        print()
        for entry in out["catapult_trajectory"]:
            print(f"  [{', '.join(entry['catapults_included'])}] depth {entry['exclusion_depth']}, "
                  f"excluded: {', '.join(entry['infantry_excluded']) or '(none)'}")
        return

    print(f"Infantry included ({len(out['infantry_included'])}): {', '.join(out['infantry_included'])}")
    print(f"Infantry excluded: {', '.join(out['infantry_excluded']) if out['infantry_excluded'] else '(none)'}")
    print()
    print(f"{'Catapult tiers':45s} {'Total squads':>13s} {'Dominance %':>12s} {'Recovery cost':>15s}")
    for entry in out["catapult_trajectory"]:
        # Actual count of nonzero Leadership stacks in the real result, NOT the assumed
        # unit always exists and always gets qty > 0; counting the real result is correct
        # since Battle Griffin V has had qty > 0 in every real run so far, but the old
        # formula would have been silently wrong if that ever stopped being true.
        total_squads = len(entry["result"]["leadership"]["stacks"])
        cost_str = f"{entry['recovery_cost']:,}" if "recovery_cost" in entry else "-"
        tiers = ', '.join(entry['catapults_included'])
        print(f"{tiers:45s} {total_squads:>13d} {entry['dom_pct']:>11.1f}% {cost_str:>15s}")


if __name__ == "__main__":
    LEADERSHIP = 36120
    DOMINANCE = 8280
    AUTHORITY = 16740
    # your current permanent bonuses by default; add a one-off captain/equipment
    # bonus with e.g. PERMANENT_BONUS_RULES + [{"pp": one_off_pct}] when one applies.
    STACK_BONUS_PCT = PERMANENT_BONUS_RULES

    result = run_calculator(LEADERSHIP, DOMINANCE, AUTHORITY, STACK_BONUS_PCT)
    print_report(result)
    print()
    print_full_death_order(result)
    print()
    comparison = compare_catapult_configs(LEADERSHIP, DOMINANCE, AUTHORITY, STACK_BONUS_PCT)
    print_catapult_config_comparison(comparison)