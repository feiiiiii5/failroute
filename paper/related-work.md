# Related Work — 已验证文献库

> **来源**：委外任务 🅒2 产出（2026-08-31），**已由主规划者用 Crossref API 逐条独立复验**：
> 15 条正文文献全部命中，标题 / 作者 / 年份与 API 记录一致。
> **恢复说明**：本文件于 2026-08-31 从会话记录中恢复重建 —— 原产出只存在于已删除的
> `07-决策与待办/委外任务结果.md` 中，未及整合即被清除。
> **08-31 第二轮（委外 P1）**：线 4 补强到 6 条独立条目；原「待核实」6 条逐条再攻，
> **3 条恢复、3 条永久弃用**（弃用记录见文末）。已验证条目由 15 条增至 **22 条**。
>
> 🔴 **纪律**：正文只允许引用本文件「已验证」区的条目。「弃用」区的条目**一律不得进入
> DRAFT.md 或 refs.bib**。
>
> **验证方法**：`api.crossref.org/works?query.bibliographic=<title>` 或
> `api.crossref.org/works/<DOI>` 命中且标题/作者一致才收录；DBLP
> （`dblp.uni-trier.de/search/publ/api`，主站 `dblp.org` 本机超时）用于定位无 DOI 的
> 会议记录与非 DOI 出处。DOI 全部来自 API 返回（2026-08-31 实查）。

---

## 已验证（22 条，可直接引用）

### 线 1 · 异常处理反模式的实证研究

| 引用 | 标题 | 做了什么 | 与本文的关系 | DOI |
|---|---|---|---|---|
| de Pádua & Shang, 2017 | Studying the Prevalence of Exception Handling Anti-Patterns | 在大型 Java 语料上量化异常处理反模式的出现率与分布 | **最直接的前驱**——本文把视角从「反模式是否存在」推进到「反模式背后是真缺陷还是有意契约」 | `10.1109/ICPC.2017.1`（亦见 `arXiv:1704.00778`，双记录已核） |
| de Pádua & Shang, 2017 | Revisiting Exception Handling Practices with Exception Flow Analysis | 用异常流分析重访开发者的异常处理实践 | 提供「处理形状」的方法论参照；本文六检测器的形状分类可与其对照 | `10.1109/SCAM.2017.16` |
| Cabral & Marques, 2007 | Exception Handling: A Field Study in Java and .NET Programs | 对 Java/.NET 程序的异常使用做实地研究，刻画捕获/吞没行为 | 经典实证基线；本文把同样的问题域搬到 Python AI/ML 代码库 | `10.1007/978-3-540-73589-2_8`（LNCS/ECOOP 2007；Crossref 记录无年份字段，年份据卷期标注） |
| Sawadpong, Allen & Williams, 2012 | Exception Handling Defects: An Empirical Study | 实证研究异常处理缺陷的类别与成因 | 支撑「异常处理是缺陷高发区」的动机陈述 | `10.1109/HASE.2012.24` |

### 线 2 · 静态分析的误报问题与开发者处置行为

| 引用 | 标题 | 做了什么 | 与本文的关系 | DOI |
|---|---|---|---|---|
| Johnson, Song, Murphy-Hill & Bowdidge, 2013 | Why Don't Software Developers Use Static Analysis Tools to Find Bugs? | 访谈研究开发者不用静态分析的原因（误报与噪音居首） | 本文的「有意契约占比」测量直接解释了为何通用规则会被开发者静音 | `10.1109/ICSE.2013.6606613` |
| Sadowski, Van Gogh, Jaspan, Söderberg & Winter, 2015 | Tricorder: Building a Program Analysis Ecosystem | Google 的分析生态：按「可操作告警」过滤、抑制与反馈闭环 | 工业界对「告警必须可操作」的系统化回应；本文给出可操作性的语义判据之一 | `10.1109/ICSE.2015.76` |
| Ayewah & Pugh, 2010 | The Google FindBugs Fixit | Google 全仓 FindBugs 修复行动：按模式优先级推进、观察修复率 | 大规模「告警→修复」数据点；本文补充「不修 = 有意契约」的另一种解释 | `10.1145/1831708.1831738` |
| Do, Wright & Ali, 2022 | Why Do Software Developers Use Static Analysis Tools? A User-Centered Study of Developer Needs and Motivations | 以用户为中心研究开发者对静态分析的真实需求与动机 | 为「规则设计应以使用者工作流为约束」提供证据 | `10.1109/TSE.2020.3004525` |
| **Ruthruff, Penix, Morgenthaler, Elbaum & Rothermel, 2008** | Predicting Accurate and Actionable Static Analysis Warnings: An Experimental Approach | ICSE 2008 实验：以「可操作 + 低误报」为标准预测并排序程序分析告警 | 与本文同一关切：告警的**可操作性**而非检出数是采纳的前提；本文用「缺陷 vs 契约」标注给可操作性一个语义度量 | `10.1145/1368088.1368135` |

### 线 3 · ML/AI 系统中的静默失败、数据级联与技术债

| 引用 | 标题 | 做了什么 | 与本文的关系 | DOI / 出处 |
|---|---|---|---|---|
| Sambasivan et al., 2021 | "Everyone wants to do the model work, not the data work": Data Cascades in High-Stakes AI | 高危 AI 系统中数据问题级联放大的田野研究 | **本文是其在代码层的对应物**——失败路由就是级联的微观机制 | `10.1145/3411764.3445518` |
| Amershi et al., 2019 | Software Engineering for Machine Learning: A Case Study | 微软 ML 平台的软件工程案例：测试、集成与运维痛点 | 佐证「ML 系统的工程实践落后于模型本身」 | `10.1109/ICSE-SEIP.2019.00042` |
| Paleyes, Urma & Lawrence, 2022 | Challenges in Deploying Machine Learning: A Survey of Case Studies | 49 个部署案例的系统综述（数据、模型、基础设施各层失效） | 为「失败发生在管线的每一层」提供综述级证据 | `10.1145/3533378` |
| Breck, Cai, Nielsen et al., 2017 | The ML Test Score: A Rubric for ML Production Readiness and Technical Debt Reduction | 提出 28 条生产就绪评分细则以削减 ML 技术债 | 其测试/监控条目与「失败要响亮」同源；本文给出可自动化检测的那一部分 | `10.1109/BigData.2017.8258038` |
| Zhang, Harman, Ma et al., 2022 | Machine Learning Testing: Survey, Landscapes and Horizons | ML 测试技术全景综述（含故障注入与鲁棒性测试） | 把静态检测放进「ML 测试谱系」的引用锚点 | `10.1109/TSE.2019.2962027` |
| Dixit et al., 2023 | Keytone: Silent Data Corruptions at Scale | 大规模集群中静默数据损坏（硬件层）的测量 | 「静默损坏」概念的硬件原型；本文论证软件层的失败路由是同款疾病的软件形态 | `10.1109/IOLTS59296.2023.10224872` |
| **Sculley, Holt, Golovin, Davydov, Phillips, Ebner, Chaudhary, Young, Crespo & Dennison, 2015** | Hidden Technical Debt in Machine Learning Systems | NeurIPS 2015：ML 系统特有的技术债（管线耦合、胶水代码、隐式依赖、反馈回路） | 本文的「失败路由」可视为其「胶水代码 / 管线耦合」债在一个具体代码模式上的可测量切片 | **无 DOI**（NeurIPS 不分配）；官方页 `https://proceedings.neurips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html`（08-31 抓取，标题/作者已核） |
| **Breck, Polyzotis, Roy, Whang & Zinkevich（MLSys 2019 会议录顺序）, 2019** | Data Validation for Machine Learning | 提出贯穿训练/服务的数据校验框架与连续性校验 | 与本文同为「让失败在管线里可见」的主张；本文聚焦异常处理层的校验缺失 | **无 DOI**；官方页 `https://proceedings.mlsys.org/paper_files/paper/2019/hash/928f1160e52192e3e0017fb63ab65391-Abstract.html`（08-31 抓取；DBLP 记录 venue 标注为 `SysML`，作者顺序与会议录页不同，引用时以会议录页为准） |

### 线 4 · Linter 的采用度与规则设计哲学

| 引用 | 标题 | 做了什么 | 与本文的关系 | DOI |
|---|---|---|---|---|
| Sadowski, Aftandilian, Eagle, Miller & Kehrer, 2018 | Lessons from Building Static Analysis Tools at Google | Google 静态分析产品化经验：按信号价值排优先级、抑制与自动修复 | 本文的精度/语义取舍与「高信噪比才可用」的工业结论互证 | `10.1145/3188720` |
| **Hu, Wang, Rubin & Pradel, 2025** | An Empirical Study of Suppressed Static Analysis Warnings | 大规模实证：开发者**抑制**哪些告警、抑制的理由与后续处置 | **与本文互补的另一半**——抑制行为解释了「规则命中 ≠ 需要修」；本文给出为什么某些命中结构上就不该修 | `10.1145/3715729` |
| **Yedida, Kang, Tu, Yang, Lo & Menzies, 2023** | How to Find Actionable Static Analysis Warnings: A Case Study With FindBugs | 用缺陷实际演化为 bug 的比例度量「可操作性」，给告警排序 | 把「可操作」变成可测量量的先例；本文把同一动作从「后来变成 bug」换成「此处是否有意契约」 | `10.1109/TSE.2023.3234206` |
| **Guo, Tan, Liu, Liu, Lai, Yang, Li, Chen & Dong, 2023** | Mitigating False Positive Static Analysis Warnings: Progress, Challenges, and Opportunities | 误报抑制方法综述：进展、开放挑战 | 为「误报是第一约束」提供综述级支撑，并说明本文不是又一个误报检测器而是误报**归因** | `10.1109/TSE.2023.3329667` |
| **Querel & Rigby, 2018** | WarningsGuru: Integrating Statistical Bug Models with Static Analysis to Provide Timely and Relevant Warnings | 用统计模型过滤相关性，只对开发者推告警 | 「按相关性而非完备性设计规则」的工业实现；本文的六规则设计哲学与之同源 | `10.1145/3236024.3264599` |
| **Crisan & McNutt, 2025** | Linting is People! Exploring the Potential of Human Computation as a Sociotechnical Linter | CHI EA 2025：把 linter 看成**社会技术系统**而非纯语法工具 | 支撑本文「linter 的产物是人要处置的告警」这一前提，而非「linter 的产物是违规计数」 | `10.1145/3706599.3716230` |

> 线 4 另两条核心（Johnson 2013、Ayewah & Pugh 2010）见线 2，不重复列。
> 线 4 补强前只有 1 条独立条目，现有 **6 条**（含 Sadowski 2018）。

---

## 🔴 弃用（再攻失败，永久不得引用）

| 候选 | 再攻记录（2026-08-31） |
|---|---|
| Tartler 等, Linux 内核异常处理实证 | DBLP `q=Holen Tartler exceptions` → total=0；`q=Linux kernel exception handling empirical Tartler` → total=0；`q=Tartler`（按标题含 exception/Linux/error 过滤）三次重试均被拒（HTTP 429 / RemoteDisconnected）。Crossref 侧（前一轮）仅命中同作者其他论文。→ **永久弃用** |
| O'Leary 等, *Making Failures Visible* | DBLP `q=failures visible` → total=4，无一条作者为 O'Leary、无一条标题匹配（Bedi 2026 / Vaz 2011 / Li 2010 ×2）。前一轮 Crossref 亦未命中。→ **永久弃用**，判定原记忆条目有误 |
| Johnson 等, *Expectations of Static Analysis Tool Users* | DBLP `q=expectations static analysis` → total=1：Utture 2023《Adapting Static Analysis Tools to Meet User Expectations》无 DOI、无 venue 记录（疑似学位论文/短篇），不足以引用。前一轮 Crossref 未命中。→ **永久弃用**；该关切已由线 2 的 Johnson 2013 + 线 4 的 Yedida 2023 / Hu 2025 覆盖 |

**原「待核实」中已恢复的 3 条**：Sculley 2015（NeurIPS 官方页，无 DOI）·
Breck 2019 Data Validation（MLSys 会议录官方页，无 DOI）·
Ruthruff 等（**原条目题名与出处均有误**：不存在 "Is the Cure Worse than the Disease?" AST 2008 这一条；
作者组合的真实工作是 ICSE 2008《Predicting Accurate and Actionable Static Analysis Warnings》，
DOI `10.1145/1368088.1368135`，已并入线 2）。
另：DBLP `q=cure worse than disease` 命中的 4 条（Smith 2015 / Guo 2013 / Vanbever 2013 / Ahmed 2025）
均非该工作，不得混用。

---

## §7 Related Work 正文草稿（英文，供主规划者替换 DRAFT.md §7 的 TODO 块）

> 2026-08-31 由委外 P1 起草。全部指涉均限本文件「已验证」区条目；
> 括注为 bibkey，见 `paper/arxiv/refs.bib`。

**Failure handling as an empirical object.** Exception handling has a long empirical literature
in statically typed languages: Cabral and Marques' field study of Java and .NET~\cite{cabral2007}
documented how often exceptions are caught and swallowed; Sawadpong et al.~\cite{sawadpong2012}
characterised exception-handling *defects*; and de Pádua and Shang quantified the prevalence of
named exception-handling anti-patterns over a large corpus~\cite{depadua2017prevalence} and
revisited developer practice through exception-flow analysis~\cite{depadua2017flow}. That line
of work asks *whether* anti-patterns occur and *how often*. Our closest neighbour is it: we
inherit the premise that handling shape is measurable, and change the question. On a corpus of
Python AI/ML packages, the same syntactic shapes that read as anti-patterns are predominantly
*intended contracts* — in our stratified sample of 80 sites, 80.0\% carried a contract reading and
5.0\% were outright false positives, with the defect share concentrated almost entirely in one
package. Reporting a prevalence number without that breakdown is what makes the earlier literature
unreadable as a triage instruction.

**Why generic rules get muted.** A second body of work explains the reception of such numbers.
Developers report false positives and noise as the leading reason they ignore or abandon static
analysis~\cite{johnson2013}; Ruthruff et al. made *actionability* an experimental target rather
than a slogan~\cite{ruthruff2008}; Google's Tricorder and FindBugs-Fixit programmes showed that
an analysis only survives at scale when it is filtered, prioritised and paired with a
suppression path~\cite{sadowski2015,ayewah2010,sadowski2018}. User-centred and follow-up studies
reach the same ordering from the other side: what developers need is a warning they can act
on~\cite{do2022,yedida2023}, and the mitigation of false positives remains an open
problem rather than a solved one~\cite{guo2023}. WarningsGuru operationalised relevance with
statistical bug models~\cite{querel2018}, and Hu et al. recently measured the other end of the
same pipe — which warnings developers actually suppress, and on what
grounds~\cite{hu2025suppressed}. Crisan and McNutt frame linting as a sociotechnical
activity~\cite{crisan2025}. Our contribution is not another relevance filter: it is a *semantic*
account of why a particular family of syntactic matches is disproportionately non-actionable, so
that a suppression decision can be justified by code shape rather than by developer fatigue.

**Silent failure in machine-learning systems.** The systems literature supplies the stakes.
Sculley et al. named the pipeline coupling and glue-code debt that makes ML behaviour
brittle~\cite{sculley2015}; Breck et al. proposed continuous data validation as the corrective at
the data boundary~\cite{breck2019}; the ML Test Score encoded "test the pipeline, not just the
model" as a rubric~\cite{breck2017}; Amershi et al. and Paleyes et al. documented that the
failures arrive at integration and deployment time, not training
time~\cite{amershi2019,paleyes2022}; Sambasivan et al. traced how a data problem cascades through
a high-stakes system until it surfaces as an unexplained
outcome~\cite{sambasivan2021}; and Dixit et al. measured silent corruption at the hardware layer
where no exception is raised at all~\cite{dixit2023}. Zhang et al. position testing and robustness
techniques across that same spectrum~\cite{zhang2022}.

**Increment over the two closest studies.** Read side by side, de Pádua and Shang~\cite{depadua2017prevalence}
and Hu et al.~\cite{hu2025suppressed} bound the problem on either side: the first measures how
often a handling shape appears, the second measures what developers do once a tool points at it.
Neither asks, *per site*, whether the flagged construct is a defect, an intended contract, or a
tool artefact — and neither reports what a purely syntactic linter fails to see at all. This
paper supplies both measurements for Python AI/ML code: a labelled 80-site sample
(12 DEFECT / 64 CONTRACT / 4 FALSE POSITIVE, with the defect mass concentrated in one package),
and a cross-tool comparison showing that four widely used syntactic linters jointly cover 39.0\%
of the 649 routed-failure sites we detect, with one entire pattern — `contextlib.suppress`-style
silent suppression — at 0/27. The increment is therefore empirical and narrow: the *meaning* of
a flagged handler, and the *coverage boundary* of the tools practitioners actually run.

---

## 🔒 本文件维护规范

| 规则 | 说明 |
|---|---|
| **权威级别** | 🥇 一级 —— 论文引用的唯一真源 |
| 🔴 **只增不降标准** | 新增条目必须先过 Crossref / arXiv API 验证，且标题/作者/年份/出处四项一致 |
| 🔴 **「弃用」区不得被引用** | 一条无法验证的引用足以让整篇 preprint 失去可信度 |
| **删除条件** | 只有在 API 复查证明记录不存在时才移出「已验证」区，并写明复查命令与日期 |
