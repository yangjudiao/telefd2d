# Optimized Prompt Package (telefd2d)

## 1) Original Request Summary
- Input prompt from `prompt_0.docx` asks to:
  - clean/organize `my_fd_topo_boost` code,
  - publish as new GitHub repo `telefd2d`,
  - write complete documentation,
  - provide bilingual (CN/EN) project intro,
  - place topo example `vx`/`vz` GIF and seismogram at top-level intro,
  - rename files/variables where needed,
  - execute in two stages (`/init` then main CLI),
  - enforce plan-first, AC per step, autonomous retry on failures,
  - keep max subagent concurrency at 2.

## 2) Gaps Detected
- GitHub target owner not explicitly specified (user or org).
- No explicit acceptance threshold for runtime/physics regression in this prompt.
- Rename scope ambiguity (public docs/scripts vs internal package/module names).
- Repo publication may be blocked by missing GitHub CLI authentication/token.

## 3) Clarification Questions (Skipped; assumptions used)
- Safe, reversible defaults are used:
  - publish target owner defaults to authenticated `gh` account,
  - rename scope defaults to user-facing docs/scripts and output naming,
  - internal package name `fd_workflow` kept stable unless functional conflict appears.

## 4) EARS Requirements
- Ubiquitous: The system shall treat the migrated project name as `telefd2d` in public-facing documentation.
- Ubiquitous: The system shall execute in two stages: `/init` then main CLI.
- Ubiquitous: The system shall produce a stepwise plan before changing files.
- Ubiquitous: The system shall define at least one measurable acceptance criterion for each execution step.
- Event-driven: When `/init` stage starts, the system shall generate/update `AGENTS.md` and both stage prompts.
- Event-driven: When main stage runs, the system shall generate an acceptance run under `output/forward_case_telefd2d`.
- Event-driven: When demo artifacts are available, the system shall copy `vx` GIF, `vz` GIF, and seismogram into `assets/topo_demo/`.
- Conditional: If a command fails, the system shall record root-cause hypothesis and run one bounded alternative attempt.
- Conditional: If GitHub push prerequisites are missing, the system shall stop before destructive retries and output exact remediation commands.
- Unwanted behavior: If user-facing docs still contain legacy project branding, the system shall prevent completion status.
- Unwanted behavior: If any mandatory demo asset is missing, the system shall prevent completion status.

## 5) Optimized Prompt (Ready to Run)

### Stage A - /init prompt
你是仓库初始化执行器。请把当前目录初始化为 `telefd2d` 的发布基线。

执行要求：
1. 先输出计划，再执行。
2. 每一步必须包含 AC（可判定 Pass/Fail）。
3. 必须生成并更新：`AGENTS.md`、`prompts/init_prompt.md`、`prompts/cli_prompt.md`、`docs/workflow_plan.md`。
4. 明确目录结构：`src/`、`scripts/`、`docs/`、`prompts/`、`assets/`、`output/`。
5. 失败时记录 RCA 并至少一次替代尝试。
6. 最大并发子代理数为 2。

初始化完成判据：
- 规则文件、两阶段提示词、计划文档全部存在。
- 计划文档中每个步骤均有 AC。
- 项目命名规则对外统一为 `telefd2d`。

### Stage B - main CLI prompt
你是 `telefd2d` 主执行 CLI。请按计划完成“整理 + 运行 + 发布准备”。

执行要求：
1. 迁移对外命名到 `telefd2d`（文档、命令示例、输出目录命名）。
2. 运行算例并生成 `output/forward_case_telefd2d/`。
3. 抽取 demo 资源到 `assets/topo_demo/`，至少包含 `wavefield_vx.gif`、`wavefield_vz.gif`、`surface_seismogram_vz.png`。
4. 更新 README，使中英双语简介和 demo 资源在页面顶部可见。
5. 初始化 git 仓库，并尝试创建/推送 GitHub 仓库 `telefd2d`。
6. 失败时记录 RCA、执行一次替代方案并重新验证 AC。

完成判据：
- 运行命令成功（mode all）。
- README 双语 + 顶部 demo 可见。
- `git status` 正常，仓库可提交；若 push 失败需给出精确阻塞原因和修复命令。

## 6) Assumptions and Risks
- Assumption: user accepts keeping internal Python package name `fd_workflow` to avoid unnecessary API breakage.
- Assumption: GitHub publication target is current authenticated account.
- Risk: if `gh auth` is absent/expired, automatic publish cannot complete.
- Risk: acceptance run depends on local Python deps and compiled extension compatibility.

## 7) Execution Report Template (for optimize-and-run)
- Actions taken
- Files changed
- Validation results (per AC)
- Failure/RCA/retry notes
- Residual risks
