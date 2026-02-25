# CLI Main Prompt (telefd2d execution)

你是 `telefd2d` 主执行 CLI。请根据下列要求完成“整理 + 运行 + 发布准备”闭环。

## Objective
- 将项目整理为 GitHub 可发布状态，并完成一组可复现实例输出。

## Constraints
1. 保持 2D staggered-grid elastic FD 的既有行为，不做物理语义回退。
2. 保持 compute/postprocess 解耦流程。
3. 文档需中英双语（至少 README 核心部分）。
4. 首页必须展示 topo 示例：`vx` GIF、`vz` GIF、seismogram。
5. 先计划后执行；每步必须有 AC。
6. 失败时必须记录 RCA，并执行至少一次替代尝试。

## Workflow
1. 执行仓库整理：更新命名、文档、命令入口。
2. 运行验收算例（`mode all`）生成 `forward_case_telefd2d`。
3. 抽取可展示资产到 `assets/topo_demo/`。
4. 更新 README 顶部展示区（中文 + English）。
5. 初始化 git 仓库并准备 GitHub 推送。

## Deliverables
- `README.md`（中英双语，顶部展示 GIF/Seismogram）
- `output/forward_case_telefd2d/`（算例产物）
- `assets/topo_demo/*`（展示素材）
- `docs/workflow_plan.md`（执行证据）

## Acceptance Criteria
- AC-M1: `python scripts/run_acceptance_case.py --mode all --output-subdir forward_case_telefd2d` 成功。
- AC-M2: `assets/topo_demo/wavefield_vx.gif`、`assets/topo_demo/wavefield_vz.gif`、`assets/topo_demo/surface_seismogram_vz.png` 至少存在并可被 README 引用。
- AC-M3: README 包含双语简介、安装步骤、运行命令、结果路径。
- AC-M4: `git status` 可正常工作，仓库处于可提交状态。
