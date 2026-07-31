# Total Battle Stack Calculator

Works out **how many of each unit to field** so your army dies in the order you
want it to, and shows you what each option costs.

In battle, the stack with the highest total stack HP dies first. That means you
control the death order by controlling quantities — field a weak unit in bulk and
it soaks the opening hits, while your genuinely tanky units survive to keep
swinging. This tool picks the quantities for you.

Built for planning epic monster hits.

## Get started

1. Download **`tb_stack_calc.py`** and **`README.txt`**
2. Read `README.txt` — it explains the whole thing, including how to put your own
   bonuses in
3. Run it with Python 3 (no libraries, no install)

**You must replace the bonus values near the top of the script with your own.**
The ones that ship with it belong to a different account, so running it unmodified
gives you a confident, precise, wrong answer.

Easiest path if you're not comfortable editing Python: hand `tb_stack_calc.py` and
`README.txt` to an AI assistant along with your own bonus totals and caps, and ask
it to configure and run it. `README.txt` has a section on exactly what to tell it.

## What it does not do

- **No damage or strength simulation.** It knows HP, unit types, bonuses and troop
  capacity costs. It cannot tell you whether you win a fight.
- **No turn order or attack priority.**
- It assumes each enemy squad destroys one of your stacks.

It answers "how do I arrange my army", not "do I win".

## Files

| File | What it is |
|---|---|
| `tb_stack_calc.py` | The calculator. One file, no dependencies. |
| `README.txt` | Full documentation — setup, configuration, reading the output. |
| `monster_citadel_db.md` | Enemy garrison compositions and stat cards for various citadels and squads. |

Public domain (Unlicense) — do whatever you like with it.
