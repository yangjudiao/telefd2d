# Optimized Prompt Package (telefd2d MCP enablement)

## 1) Original Request Summary
- Source: `prompt_0.docx`
- User asks to:
  - assess whether telefd2d is suitable for MCP integration so AI can run forward modeling quickly,
  - recommend a better option if MCP is not optimal,
  - implement MCP (or chosen better option),
  - update GitHub-facing project files, documentation, and examples comprehensively,
  - run with plan-first discipline and AC for every step,
  - auto-diagnose and iterate on failures,
  - use at most two subagents,
  - generate two prompts (`/init` and main CLI), and execute in stage order.

## 2) Gaps Detected
- Target GitHub push permissions are unknown in the current environment.
- Runtime budget for full-scale physics acceptance is not explicitly bounded.
- No fixed minimum MCP tool set is specified by the source prompt.

## 3) Clarification Questions
- Skipped with reversible defaults:
  - choose MCP as primary integration path and keep CLI as execution backend,
  - validate with lightweight baseline smoke run first,
  - keep internal numerical package names unchanged for compatibility.

## 4) EARS Requirements
- Ubiquitous: The system shall produce a stepwise execution plan before making code changes.
- Ubiquitous: The system shall define at least one measurable acceptance criterion per step.
- Ubiquitous: The system shall execute in two stages: `/init` then main CLI.
- Event-driven: When `/init` stage starts, the system shall generate/update `AGENTS.md`, `prompts/init_prompt.md`, `prompts/cli_prompt.md`, and this optimized package file.
- Event-driven: When main stage runs, the system shall implement MCP tools that can run telefd2d forward modeling and read outputs.
- Conditional: If command execution fails, the system shall record RCA and perform at least one bounded retry/fallback.
- Conditional: If MCP runtime dependencies are missing, the system shall provide exact install commands and prevent false completion.
- Unwanted behavior: If required MCP docs and examples are missing, the system shall prevent completion status.
- Unwanted behavior: If smoke-test output lacks metadata files, the system shall prevent completion status.

## 5) Optimized Prompt (Ready to Use)

### Stage A - /init Prompt
你是 telefd2d 的初始化执行器，请建立“AI 可调用（MCP）”的实施基线。

执行规则：
1. 先计划后执行。
2. 每一步必须定义 AC（Pass/Fail）。
3. 必须更新：`AGENTS.md`、`prompts/init_prompt.md`、`prompts/cli_prompt.md`、`prompts/optimized_prompt_package.md`、`docs/workflow_plan.md`。
4. 输出并校验 MCP 相关结构规划：`src/telefd2d_mcp/`、`scripts/run_mcp_server.py`、`docs/mcp_integration.md`。
5. 失败时记录 RCA，并至少一次重试或替代尝试。
6. 最大子代理并发 2。

完成判据：
- 初始化文件齐全；
- 每步有 AC；
- MCP 路径和命名规范可检索。

### Stage B - Main CLI Prompt
你是 telefd2d 主执行 CLI，请按计划完成 MCP 方案决策、实现、验证与文档闭环。

执行规则：
1. 先做技术决策：MCP 是否优于纯脚本/REST，并写入决策文档。
2. 实现 MCP server，至少提供工具：
   - `telefd2d_summarize_project`
   - `telefd2d_run_forward_case`
   - `telefd2d_get_case_report`
   - `telefd2d_list_cases`
3. MCP 工具必须做参数校验，禁止路径穿越式输出目录输入。
4. 新增 `scripts/mcp_smoke_test.py` 并完成一次可复现 smoke run。
5. 更新 README（中英）和 docs，包含：
   - 安装命令
   - MCP 启动命令
   - 至少一个工具调用示例
   - 验收标准
6. 对失败记录 RCA 并至少一次重试后再给结论。

完成判据：
- `python scripts/mcp_smoke_test.py --backend baseline` 成功；
- 产物目录存在 `compute_metadata.json` 和 `run_metadata.json`；
- README 系列包含 MCP 快速开始；
- 形成执行证据文档（步骤、AC、结果）。

## 6) Assumptions and Risks
- Assumption: keep `fd_workflow` internal package unchanged for compatibility.
- Assumption: smoke test with baseline backend is acceptable as first-gate validation.
- Risk: no Git remote auth in this environment may block direct push.
- Risk: large production runs may require boost extension and longer execution budget.

## 7) Execution Report Template (optimize-and-run)
- Actions taken
- Files changed
- Validation results by AC
- Failure/RCA/retry evidence
- Residual risks and next actions
