# FailRoute arXiv 最终投稿指南

本次已准备修订后的28页论文，未替你登录、上传或点击Submit Article。旧取消稿已保存在桌面工作区的 `archive-cancelled-20261111/`，不要再上传它。GitHub固定版本为 `arxiv-20261111-final`。

## 先确认入口

- 如果原稿尚未公开、只是Unsubmit：打开同一条 incomplete submission，更新文件和metadata后重新提交，不要重复创建同一文章。
- 如果原稿已在公告前Delete：可以使用Start New Submission重新开始。
- 如果实际已有公开arXiv ID：使用该文章的Replace，不要另投一篇重复稿。
- 如果页面是On Hold：不要删除重投，按官方联系流程处理。

用户已告知取消成功；本任务没有独立读取账户状态，所以以你的arXiv账号页面为准。

## 本地文件

桌面 `failroute-arxiv-20261111/`：

- 推荐上传：`failroute-arxiv-upload-all-2026-11-11.tar.gz`，包含根目录main.tex、refs.bib、main.bbl、三张图，以及anc/中的复核材料。
- 仅论文源码：`failroute-arxiv-source-2026-11-11.tar.gz`，六个必需文件。若不上传附属证据，用这一份即可。
- 可选附属材料：`failroute-arxiv-ancillary-2026-11-11.tar.gz`，内容在anc/目录。使用推荐合并包时不要再上传这一份。
- `main.pdf`：你审核使用的最终PDF，不替代LaTeX源码上传。
- `abstract-form.txt`、`metadata.md`：表单内容；`SHA256SUMS.txt`用于本地校验。

不要同时上传多个相互重复的主源码包，不上传旧PDF、备份目录、日志、aux/out文件、Python语料目录或虚拟环境。

## 上传和编译

1. 登录 https://arxiv.org/user ，按上面状态选择Update或Start New Submission。
2. 阅读并由你本人确认所有权、作者同意与提交协议。许可与当前论文一致为CC BY 4.0，但请先确认资助方、学校和未来投稿要求；公开后该版本许可不可撤销。
3. 主分类选 Computer Science / Software Engineering（cs.SE）。默认不加cross-list；首次该分类投稿如要求endorsement，按页面完成，不虚构推荐资格。
4. 上传推荐的合并tar.gz，执行Check Files，确认根目录主文件是main.tex，三张图路径完整，anc/被识别为附属材料。若平台提示某附属文件不接受，可改用六文件主源码包，证据仍在固定GitHub版本可访问。
5. 编译器选PDFLaTeX，TeX Live 2025（当前默认；2023也受支持）。本地用Tectonic已从干净源码编译通过，但arXiv服务端编译必须在页面再核对。不要添加不必要的pdfoutput命令。
6. 下载并逐页看arXiv生成的PDF，与本地main.pdf对照：28页、4图、14表、25条参考文献；第1页摘要不再将3/14、5/14、9/14当作结论，第17页为16例审计状态图，参考文献从第27页开始。编译页数或分页变化不一定是错，但须检查所有图表和交叉引用。
7. 如出现缺图、缺引用、乱码、裁切、旧摘要或报错，先修正上传文件，不要绕过检查提交。

## 填写metadata

Title:
Measuring What a Failure-Routing Detector Adds: Representation, Calibration, and Validation Limits

Authors:
Yufeiyang Chen

Affiliation（若表单要求）:
School of Cyber Science and Technology, Sun Yat-sen University, Shenzhen, China

Primary category:
cs.SE

Comments:
28 pages, 4 figures. Code, data and reproduction scripts: https://github.com/feiiiiii5/failroute/tree/arxiv-20261111-final

Abstract:
粘贴同目录abstract-form.txt，1868字符，不加Abstract标题。它已改成ASCII和纯文本；%无需加反斜杠。检查页面预览与PDF含义一致。

Journal-ref、DOI、Report number：留空。此稿尚无已核实的正式出版信息。不要填写虚构DOI或accepted。

## 最后提交前由你确认

作者姓名、单位、公开邮箱fei76161@gmail.com和AI辅助/作者责任陈述是否准确；有无还需披露的资助或利益关系；许可是否可以接受；页面生成PDF和metadata是否确为本次版本。

检查完毕，由你本人点击Submit Article。保存确认邮件和submission ID。此前尚未公开时重交通常重新排队，不能保证公告时间或cs.SE审核通过。2026-11-11为arXiv假日，不要期待当天公告。这里说“可投稿”是源码、证据和已识别错误修复到位，不是同行评审结论或arXiv接收保证。

## 官方依据

- 投稿流程：https://info.arxiv.org/help/submit/index.html
- TeX要求：https://info.arxiv.org/help/submit_tex.html
- 编译环境：https://info.arxiv.org/help/faq/texlive.html
- Metadata：https://info.arxiv.org/help/prep.html
- 许可：https://info.arxiv.org/help/license/index.html
- 状态：https://info.arxiv.org/help/submit_status.html
- 已公开文章修订：https://info.arxiv.org/help/replace.html
- Ancillary files：https://info.arxiv.org/help/ancillary_files.html

## 保留的研究限制

这是一篇measurement case study。没有独立人类缺陷标注，不报告新增缺陷precision/recall；四基线不能代表所有静态分析器；Semgrep部分解析被透明标为PARTIAL；两个heldout name-shadowing映射失败原样保留；样本是目的性选择，稳健性分析为post-hoc。具体复现日志见仓库paper/FINAL-VALIDATION.md。没有用新数字掩盖旧比例问题。
