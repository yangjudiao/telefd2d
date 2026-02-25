# /init Prompt (telefd2d bootstrap)

你是该仓库的初始化执行器。目标是把现有 FD 代码库整理成可直接发布的 `telefd2d` 项目基线。

## Objective
- 在不破坏现有物理计算链路的前提下，完成仓库初始化、规则文件、两阶段提示词和执行计划落盘。

## Inputs
- 源项目：`D:\works_1\my_fd_topo_boost_0`
- 目标仓库目录：当前目录（仓库名对外统一为 `telefd2d`）

## Hard Constraints
1. 先计划，后执行。
2. 每一步必须有可判定 AC（Acceptance Criteria）。
3. 失败后必须给出 RCA，并执行至少一次替代尝试。
4. 最多 2 个子代理并发。
5. 生成并更新 `AGENTS.md`。

## Required Actions
1. 确认目录结构可发布：`src/`、`scripts/`、`docs/`、`prompts/`、`assets/`、`output/`。
2. 生成/更新：
   - `AGENTS.md`
   - `prompts/init_prompt.md`
   - `prompts/cli_prompt.md`
   - `prompts/optimized_prompt_package.md`
   - `docs/workflow_plan.md`
3. 在计划中写清主线步骤、每步 AC、执行记录位。

## Acceptance Criteria
- AC-I1: 规则文件和双阶段提示词存在且内容与 `telefd2d` 目标一致。
- AC-I2: `docs/workflow_plan.md` 包含步骤、命令、AC、结果记录。
- AC-I3: 目录中存在 `assets/topo_demo/` 占位路径或已填充资源。
