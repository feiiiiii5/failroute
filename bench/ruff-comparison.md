# failroute vs ruff S110/S112 -- real AI/eval repositories

Run: 2026-08-29 05:12 UTC

| Repo | scanned path | failroute total | no-action | semantic (fallback+masked) | silent-suppress | ruff S110/S112 | overlap | failroute-only |
|---|---|---|---|---|---|---|---|---|
| garak | `/Users/fei/Desktop/申请季/Open source/garak/garak` | 21 | 6 | 15 | 0 | 9 | 4 | 17 |
| inspect_ai | `/Users/fei/Desktop/申请季/Open source/inspect_ai-fork/src/inspect_ai` | 370 | 146 | 223 | 8 | 55 | 52 | 318 |
| pydantic_ai_slim | `/Users/fei/Desktop/申请季/Open source/pydantic-ai/pydantic_ai_slim` | 111 | 27 | 81 | 19 | 4 | 4 | 107 |
| uqlm | `/Users/fei/Desktop/申请季/Open source/uqlm/uqlm` | 17 | 8 | 9 | 0 | 2 | 2 | 15 |
| trl | `/Users/fei/Desktop/申请季/Open source/trl/trl` | 26 | 9 | 17 | 0 | 2 | 2 | 24 |
| smolagents | `/Users/fei/Desktop/申请季/Open source/smolagents/src/smolagents` | 15 | 9 | 6 | 0 | 1 | 1 | 14 |
| deepteam | `/Users/fei/Desktop/申请季/Open source/deepteam-fork/deepteam` | 162 | 10 | 152 | 0 | 6 | 5 | 157 |
| fickling | `/Users/fei/Desktop/申请季/Open source/fickling/fickling` | 16 | 2 | 14 | 0 | 0 | 0 | 16 |
| **total** | 738 | 217 | 517 | 79 | 70 | 668 |

`semantic` = silent-fallback + masked-exception: the failure-to-success conversion class that ruff S110/S112 cannot express by construction. `silent-suppress` = `with contextlib.suppress(...)`: semantically identical to except+discard, but invisible to every shipped syntactic linter.
