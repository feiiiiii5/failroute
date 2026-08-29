# failroute vs ruff S110/S112 -- real AI/eval repositories

Run: 2026-08-29 05:09 UTC

| Repo | scanned path | failroute total | no-action | semantic (fallback+masked) | silent-suppress | ruff S110/S112 | overlap | failroute-only |
|---|---|---|---|---|---|---|---|---|
| garak | `/Users/fei/Desktop/申请季/Open source/garak` | 7273 | 2528 | 4621 | 177 | 13 | 4 | 7269 |
| inspect_ai-fork | `/Users/fei/Desktop/申请季/Open source/inspect_ai-fork` | 598 | 295 | 302 | 31 | 109 | 104 | 494 |
| pydantic-ai | `/Users/fei/Desktop/申请季/Open source/pydantic-ai` | 186 | 49 | 130 | 24 | 10 | 7 | 179 |
| uqlm | `/Users/fei/Desktop/申请季/Open source/uqlm` | 20 | 11 | 9 | 0 | 2 | 2 | 18 |
| trl | `/Users/fei/Desktop/申请季/Open source/trl` | 40 | 19 | 21 | 0 | 9 | 8 | 32 |
| smolagents | `/Users/fei/Desktop/申请季/Open source/smolagents` | 39 | 18 | 17 | 0 | 7 | 6 | 33 |
| deepteam-fork | `/Users/fei/Desktop/申请季/Open source/deepteam-fork` | 162 | 10 | 152 | 0 | 6 | 5 | 157 |
| fickling | `/Users/fei/Desktop/申请季/Open source/fickling` | 18 | 2 | 16 | 0 | 0 | 0 | 18 |
| **total** | 8336 | 2932 | 5268 | 156 | 136 | 8200 |

`semantic` = silent-fallback + masked-exception: the failure-to-success conversion class that ruff S110/S112 cannot express by construction. `silent-suppress` = `with contextlib.suppress(...)`: semantically identical to except+discard, but invisible to every shipped syntactic linter.
