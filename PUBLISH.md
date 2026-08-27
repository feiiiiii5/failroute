# PyPI 发布手册（failroute）

> 构建已完成于 `dist/`；发布需要账号凭证，属用户动作。发布后把 `action/action.yml`
> 的 `failroute-version` 默认值保持与已发布版本一致。

## 一次性：创建 API token

1. https://pypi.org/manage/account/token/ → 创建 token（Scope: Entire account 或
   限定到 `failroute` 项目，首次发布需 account 级）。

## 发布

```bash
cd 新项目-failroute
UV_PUBLISH_TOKEN=<token> /Users/fei/.local/bin/uv publish dist/*
# 或：.venv/bin/python -m pip install twine && .venv/bin/python -m twine upload dist/*
```

## 发布后验证

```bash
.venv/bin/python -m pip download failroute==0.3.0 --no-deps -d /tmp/fr-check
# 或浏览器打开 https://pypi.org/project/failroute/
```

## 重新构建（版本号变更后）

```bash
rm -rf dist && /Users/fei/.local/bin/uv build
```

注意：同版本号不可重复发布；升版需同步改 `pyproject.toml`、
`src/failroute/__init__.py`、`CHANGELOG.md`、`action/action.yml` 四处。
