# failroute vs ruff S110/S112 -- real AI/eval repositories

Run: 2026-08-29 05:34 UTC

| Repo | scanned path | failroute total | no-action | semantic (fallback+masked) | silent-suppress | ruff S110/S112 | overlap | failroute-only |
|---|---|---|---|---|---|---|---|---|
| garak | `/Users/fei/Desktop/申请季/Open source/garak/garak` | 16 | 6 | 10 | 0 | 9 | 4 | 12 |
| inspect_ai | `/Users/fei/Desktop/申请季/Open source/inspect_ai-fork/src/inspect_ai` | 346 | 146 | 199 | 8 | 55 | 52 | 294 |
| pydantic_ai_slim | `/Users/fei/Desktop/申请季/Open source/pydantic-ai/pydantic_ai_slim` | 103 | 27 | 73 | 19 | 4 | 4 | 99 |
| uqlm | `/Users/fei/Desktop/申请季/Open source/uqlm/uqlm` | 14 | 8 | 6 | 0 | 2 | 2 | 12 |
| trl | `/Users/fei/Desktop/申请季/Open source/trl/trl` | 24 | 9 | 15 | 0 | 2 | 2 | 22 |
| smolagents | `/Users/fei/Desktop/申请季/Open source/smolagents/src/smolagents` | 13 | 9 | 4 | 0 | 1 | 1 | 12 |
| deepteam | `/Users/fei/Desktop/申请季/Open source/deepteam-fork/deepteam` | 142 | 10 | 132 | 0 | 6 | 5 | 137 |
| fickling | `/Users/fei/Desktop/申请季/Open source/fickling/fickling` | 12 | 2 | 10 | 0 | 0 | 0 | 12 |
| **total** | 670 | 217 | 449 | 79 | 70 | 600 |

`semantic` = silent-fallback + masked-exception: the failure-to-success conversion class that ruff S110/S112 cannot express by construction. `silent-suppress` = `with contextlib.suppress(...)`: semantically identical to except+discard, but invisible to every shipped syntactic linter.
