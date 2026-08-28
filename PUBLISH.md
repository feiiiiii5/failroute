# PyPI 发布手册（failroute）

> **v0.4.0 已发布（2026-08-28）并端到端验证**：tag `v0.4.0` 触发 `release.yml`
> 自动构建并发布；干净 venv `pip install failroute` 安装到 0.4.0、CLI 正常。
> 仓库主页已指向 PyPI 项目页。

## 发布（当前流程：tag 触发，全自动）

1. 版本号同步四处：`pyproject.toml`、`src/failroute/__init__.py`、
   `CHANGELOG.md`、`action/action.yml`（如有版本 pin）。
2. `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`
3. GitHub Actions 的 `Release` 工作流执行 `uv build` + 发布：
   - 首选 PyPI Trusted Publishing（OIDC，无 token）——需在 PyPI 上
     failroute 项目 → Settings → Publishing 配置 owner/repository/workflow
     三项与声明一致；
   - 备用：repo secret `PYPI_API_TOKEN` 存在时走 API token 认证
     （当前生效路径，secret 不入仓、不落盘）。
4. 发布成功后建议顺手创建 GitHub Release（从 CHANGELOG 对应节生成说明）。

## 发布后验证（三步）

```bash
curl -s https://pypi.org/pypi/failroute/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
uv venv /tmp/fr-e2e && uv pip install --python /tmp/fr-e2e/bin/python failroute
/tmp/fr-e2e/bin/failroute --version
```

同版本号不可重复发布；若发布错误版本需走 PyPI 的 yank/删除流程，无法覆盖重传。
凭证一律不入仓、不落盘；聊天/日志中暴露过的 token 应到 PyPI 账号设置轮换。
