# scan-ledger.md — failroute 上游证据台账

> 状态机（对齐 `oss-agent/AGENTS.md` §12.1）：
> `NEW → RESEARCHED → QUEUED → GATES_PASSED → SUBMITTED → { CONFIRMED | MERGED | CLOSED_REJECTED | STALE }`
> 纪律：同一缺陷同一仓库只允许一条在途；对外提交前必须完成失效后果链论证；一次礼貌跟进。
> 版本：2026-08-27（首轮调研）。所有扫描均可复现：`tools/compare_ruff.py` / `failroute --repo`。

---

## 一、聚合扫描结果（08-27 实测，源包口径）

| 仓库（源包） | 语义级发现 | 说明 |
|---|---|---|
| confident-ai/deepteam | 130 | **系统性模式**：~40 个 metric 类同构缺陷，见 D-1/D-2 |
| UK AISI inspect_ai | 174 | 集中于 TUI/压缩/网络等基建层，逐点待读 |
| pydantic-ai (slim) | 55 | `_utils`/`_agent_graph` 为主，逐点待读 |
| microsoft/PyRIT | 65 | 抽样 12 处全部为有意契约，见 P-1 |
| trl | 14 | experimental 区为主，逐点待读 |
| garak | 8 | `_plugins.py` 3 处 masked-exception，逐点待读 |
| smolagents / uqlm / fickling | 4 / 3 / 8 | 逐点待读 |

完整数字见 `新项目-failroute/bench/ruff-comparison.{md,json}`。

---

## 二、条目明细

### D-1 ｜ confident-ai/deepteam ｜ metric 初始化裸 except 吞掉 system_prompt 获取失败
- 状态：**SUBMITTED**（2026-08-27，与 D-2 合并为一条主 issue：**confident-ai/deepteam#270**；正文存档 `.issue-draft-deepteam.md`（本地，未入库）。核对表全过：无同类 issue（08-27 实测 0 命中）、无 CONTRIBUTING/模板（仓库无规范文件，公开 issue 即合规渠道）、失效链独立成立、附 v1.0.9 最小复现、同仓同缺陷单条在途）
- 位置：`deepteam/metrics/*/[metric].py` `__init__`，约 40 个文件同构（样例 `metrics/bias/bias.py:46-49`，v1.0.9）
  ```python
  try:
      self.system_prompt = model.get_system_prompt()
  except:                                  # 裸 except：连 KeyboardInterrupt 也吞
      self.system_prompt = ""
  ```
- 失效后果链：自定义/错误配置的 `DeepEvalBaseLLM` 不支持 `get_system_prompt()` → 初始化静默降级为空 prompt → 全部后续评分在与用户意图不符的判据下运行 → **红队报告的易受性结论整体失真，且无任何日志或异常可追查**。
- 建议修法：窄化为 `except AttributeError`（能力探测）并记录一次警告；其余异常应上抛。
- 提交前置：读上游 CONTRIBUTING/issue 模板（Five Gates §Convention）；正文附复现代码段。
- 后续：一次礼貌跟进窗口 = 提交后 30 天；无论回应与否，旗舰叙事不依赖此条（L3 定位）。

### D-2 ｜ confident-ai/deepteam ｜ `is_successful` 的死比较掩盖评分失败
- 状态：**SUBMITTED**（并入 #270，同一次提交，避免重复条目）
- 位置：所有 RT metric（样例 `metrics/hallucination/hallucination.py:225-228`）
  ```python
  try:
      self.score == 1        # 比较表达式从不抛异常 → except 分支为死代码
  except:
      self.success = False
  return self.success
  ```
- 失效后果链：`score` 为 `None`（评测从未产生有效分）时 `None == 1` 平静返回 `False`，`except` 永不触发 → `is_successful()` 返回**上一轮残留的 `self.success`** → 一次失败的评测可能被汇报为"通过" → 红队结论出现假阳性/假阴性且不可察觉。正确语义应为 `self.score is not None and self.score == 1`（或由 `self.error` 统一裁决）。
- 备注：与已合并的 deepeval `HallucinationMetric` verdict/score 分歧缺陷同族——"评分失败被路由成成功样结果"正是 failroute 的目标类别。
- 提交前置：同 D-1；建议 D-1 + D-2 合并为一条"metric 失败路由"主 issue（避免重复提交、避免刷量观感）。**已按此执行（#270）。**

### P-1 ｜ microsoft/PyRIT ｜ 抽样 triage 结论：低价值，不提交
- 状态：**RESEARCHED → 关闭（不提交）**
- 事实：上游源码 65 条语义级发现，人工抽样 12 处（gcg_attack、attack_service 游标、converter_service、remote_dataset_loader、storage、azure_sql_memory、notebook_utils 等）——**全部是有意契约**（非法输入返回 None 重启分页、能力探测、存在性检查、URL 校验）。唯一例外 `gcg_attack.py:226 _get_control_length` 仅影响一行日志，属装饰性。
- 意义：这是"宁可少提不可刷量"纪律的实证样本，也是工具诚实度的证据（写进 write-up：误报主要来自对契约语义的机器不可知，靠人工 triage 收敛）。

### Q-1..Q-5 ｜ inspect_ai / pydantic-ai / garak / trl / uqlm ｜ 候选池（未逐点阅读）
- 状态：**NEW**（仅机器发现，未读代码前一律不得对外）
- 下一步：按失效后果链标准逐点读；预计淘汰率高（参照 P-1 经验）。garak `_plugins.py:431/442/470` 三处 masked-exception 优先级最高（插件加载失败路径直接影响扫描结论）。

---

## 三、提交纪律核对表（每次提交前逐条打勾）

- [ ] 上游无同类/在途 issue（`gh search issues` + `gh issue list`，实测记录日期）
- [ ] 已读该仓 CONTRIBUTING / issue 模板 / DCO 要求
- [ ] 失效后果链一段话可独立成立（不依赖工具术语）
- [ ] 附最小复现（文件+行号+代码段，基于提交当日 main 分支）
- [ ] 本台账状态迁移已记录，且同仓同缺陷无在途条目
- [ ] 表述不含任何未合并/未确认的预设（红线：只写已发生状态）
