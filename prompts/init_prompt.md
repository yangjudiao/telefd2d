# /init Prompt (telefd2d MCP bootstrap)

你是仓库初始化执行器。目标是把当前 `telefd2d` 仓库初始化到“AI 可调用（MCP）”的执行基线。

## Objective
- 在不改变数值核心行为的前提下，为 MCP 集成建立规则文件、阶段提示词、实施计划和文档骨架。

## Hard Constraints
1. 先输出计划，再执行。
2. 每一步必须写出可判定的 AC（Pass/Fail）。
3. 失败时必须记录 RCA，并进行至少一次有边界的重试/替代方案。
4. 最多 2 个子代理并发。
5. 必须更新 `AGENTS.md`。

## Required Actions
1. 校验项目结构：
   - `src/fd_workflow/`
   - `src/telefd2d_mcp/`
   - `scripts/`
   - `docs/`
   - `prompts/`
2. 生成或更新：
   - `AGENTS.md`
   - `prompts/init_prompt.md`
   - `prompts/cli_prompt.md`
   - `prompts/optimized_prompt_package.md`
   - `docs/workflow_plan.md`
   - `docs/mcp_decision.md`
   - `docs/mcp_integration.md`
3. 明确 MCP 运行入口与调用方式：
   - `scripts/run_mcp_server.py`
   - tool names with `telefd2d_*` prefix

## Acceptance Criteria
- AC-I1: 规则文件、阶段提示词、执行计划齐全并与 MCP 目标一致。
- AC-I2: MCP 设计决策和接入文档存在且可读。
- AC-I3: 运行入口路径与工具命名规范在文档中可检索。
