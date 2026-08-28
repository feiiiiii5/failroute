# PyPI 发布手册（failroute）

> **v0.5.0 / v0.5.1 已发布（2026-08-28）并端到端验证**：tag 触发 `release.yml`
> 自动构建、经 PyPI Trusted Publishing（OIDC，无 token）发布，并自动从
> CHANGELOG 生成 GitHub Release（`tools/release_notes.py`）。干净 venv
> `pip install failroute` 安装验证通过。

## 发布（当前流程：tag 触发，全自动）

1. 版本号同步四处：`pyproject.toml`、`src/failroute/__init__.py`、
   `CHANGELOG.md`（新增对应版本节——GitHub Release 说明取自这里）、
   `action/action.yml`（默认安装版本）。
2. `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`
3. GitHub Actions 的 `Release` 工作流执行 `uv build` → OIDC 发布 →
   用 CHANGELOG 对应节创建 GitHub Release（幂等，已存在则跳过）。
4. 发布成功后验证（见下）。

## 发布后验证（三步）

```bash
curl -s https://pypi.org/pypi/failroute/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
uv venv /tmp/fr-e2e && uv pip install --python /tmp/fr-e2e/bin/python failroute
/tmp/fr-e2e/bin/failroute --version
```

同版本号不可重复发布；若发布错误版本需走 PyPI 的 yank/删除流程，无法覆盖重传。
凭证一律不入仓、不落盘；聊天/日志中暴露过的 token 应到 PyPI 账号设置轮换。
