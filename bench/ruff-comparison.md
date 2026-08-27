# failroute vs ruff S110/S112 -- real AI/eval repositories

Run: 2026-08-27 11:07 UTC

| Repo | failroute total | no-action | semantic (fallback+masked) | ruff S110/S112 | overlap | failroute-only |
|---|---|---|---|---|---|---|
| garak | 14 | 6 | 8 | 9 | 4 | 10 |
| src | 354 | 180 | 170 | 56 | 52 | 302 |
| pydantic_ai_slim | 82 | 27 | 53 | 4 | 4 | 78 |
| uqlm | 11 | 8 | 3 | 2 | 2 | 9 |
| trl | 23 | 9 | 14 | 2 | 2 | 21 |
| src | 13 | 9 | 4 | 1 | 1 | 12 |
| deepteam | 140 | 10 | 130 | 6 | 5 | 135 |
| fickling | 10 | 2 | 8 | 0 | 0 | 10 |
| **total** | 647 | 251 | 390 | 80 | 70 | 577 |

`semantic` = silent-fallback + masked-exception: the failure-to-success conversion class that ruff S110/S112 cannot express by construction.
