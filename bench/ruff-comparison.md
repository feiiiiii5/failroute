# failroute vs ruff S110/S112 -- real AI/eval repositories

Run: 2026-08-28 03:27 UTC

| Repo | scanned path | failroute total | no-action | semantic (fallback+masked) | silent-suppress | ruff S110/S112 | overlap | failroute-only |
|---|---|---|---|---|---|---|---|---|
| garak | `/Users/fei/Desktop/申请季/Open source/garak/garak` | 13 | 6 | 7 | 0 | 9 | 4 | 9 |
| inspect_ai | `/Users/fei/Desktop/申请季/Open source/inspect_ai-fork/src/inspect_ai` | 303 | 136 | 166 | 7 | 53 | 49 | 254 |
| pydantic_ai_slim | `/Users/fei/Desktop/申请季/Open source/pydantic-ai/pydantic_ai_slim` | 98 | 27 | 69 | 20 | 4 | 4 | 94 |
| uqlm | `/Users/fei/Desktop/申请季/Open source/uqlm/uqlm` | 14 | 8 | 6 | 0 | 2 | 2 | 12 |
| trl | `/Users/fei/Desktop/申请季/Open source/trl/trl` | 22 | 9 | 13 | 0 | 2 | 2 | 20 |
| smolagents | `/Users/fei/Desktop/申请季/Open source/smolagents/src/smolagents` | 13 | 9 | 4 | 0 | 1 | 1 | 12 |
| deepteam | `/Users/fei/Desktop/申请季/Open source/deepteam-fork/deepteam` | 140 | 10 | 130 | 0 | 6 | 5 | 135 |
| fickling | `/Users/fei/Desktop/申请季/Open source/fickling/fickling` | 10 | 2 | 8 | 0 | 0 | 0 | 10 |
| **total** | 613 | 207 | 403 | 77 | 67 | 546 |

`semantic` = silent-fallback + masked-exception: the failure-to-success conversion class that ruff S110/S112 cannot express by construction. `silent-suppress` = `with contextlib.suppress(...)`: semantically identical to except+discard, but invisible to every shipped syntactic linter.
