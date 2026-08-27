# PyPI 发布手册（failroute）

> **v0.3.0 已发布（2026-08-27）并端到端验证**：干净环境 `pip install failroute==0.3.0`
> 安装成功、`failroute --version` 正常、示例检测正确。凭证一律不入仓、不落盘。
> 后续升版：版本号同步改 `pyproject.toml`、`src/failroute/__init__.py`、
> `CHANGELOG.md`、`action/action.yml` 四处，`uv build` 后用本地凭证 `uv publish dist/*`。

## 发布（后续版本）

```bash
cd 新项目-failroute
rm -rf dist && /Users/fei/.local/bin/uv build
UV_PUBLISH_TOKEN=<本地保存的 token> /Users/fei/.local/bin/uv publish dist/*
```

## 发布后验证（三步）

```bash
curl -s https://pypi.org/pypi/failroute/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
uv venv /tmp/fr-e2e && uv pip install --python /tmp/fr-e2e/bin/python failroute
/tmp/fr-e2e/bin/failroute --version
```

同版本号不可重复发布；若发布错误版本需走 PyPI 的 yank/删除流程，无法覆盖重传。
