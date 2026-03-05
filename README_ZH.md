[切换到英文](README_EN.md)

# telefd2d

telefd2d 是一个面向地形起伏与近地表地球物理场景的二维交错网格弹性波有限差分（FD/FDM）工具。

检索关键词：telefd2d、seismic、seismology、2D elastic wave、finite difference、staggered grid、wave propagation、topography、CPML、geophysics。
仓库地址：https://github.com/yangjudiao/telefd2d

## 展示画廊（PML 加厚 2 倍算例）

以下展示使用 x 和 z 两个方向均加厚到 2 倍的 PML（`--pml-x-scale 2 --pml-z-scale 2`）。

### 波场 Vx
![Wavefield Vx](assets/topo_demo/wavefield_vx.gif)

### 波场 Vz
![Wavefield Vz](assets/topo_demo/wavefield_vz.gif)

### 地表检波 Vx 记录
![Surface Seismogram Vx](assets/topo_demo/surface_seismogram_vx.png)

### 地表检波 Vz 记录
![Surface Seismogram Vz](assets/topo_demo/surface_seismogram_vz.png)

## 核心能力

- 基于交错网格的一阶速度-应力弹性波有限差分求解框架。
- 面向复杂自由表面地形的参数修正（PM）处理机制。
- 可调吸收边界（CPML 风格参数化），适配不同频率与入射条件。
- 多后端计算模式：基线 Python、C++ 串行、C++ OpenMP 并行。
- 计算与后处理解耦，支持先算后绘、重复出图。
- 支持流式落盘，降低大规模算例内存占用。
- 输出结构可追踪，便于做一致性验证和性能对比。

## 技术路线

### 1. 控制方程与离散框架
系统采用弹性波一阶速度-应力方程，并在交错网格上离散。这个框架在异质介质下具有较好的稳定性和工程可控性，也是后续边界与地形处理的基础骨架。

### 2. 地形与自由表面实现
顶部不规则地形在离散网格上表达，并通过参数修正（PM）思路处理自由表面条件。核心思想是把边界影响预先转化为边界附近介质参数修改，从而避免每个时间步都写复杂边界特判。

### 3. 吸收边界实现
左右和底部采用 CPML 风格吸收策略。通过 `pml_reflect_coeff`、`pml_power`、`pml_kappa_max` 及缩放参数控制吸收特性，以兼顾边界反射抑制与数值稳定。

### 4. 震源与观测抽象
震源参数（例如 Ricker 子波、入射角设定）与接收方式（地表记录）分离定义，保证算例配置清晰、可复现、可比较。

### 5. 计算阶段组织
计算阶段输出原始波场数组与元数据（`compute_metadata.json`），支持内存模式和流式落盘模式。这样可以在工作站硬件上更稳妥地运行大尺度算例。

### 6. 后处理阶段组织
后处理阶段读取原始输出并生成 `p`、`curl`、波场 GIF 与 seismogram 图件。由于与计算解耦，出图样式调整不需要重复完整正演。

### 7. 验证与迭代闭环
通过独立脚本分别跟踪内存行为、速度收益和结果一致性，使优化过程有证据、有门槛，减少“提速后物理回退”的风险。

## 快速开始

### 1）安装依赖
```powershell
python -m pip install -r requirements.txt
```

### 2）编译加速扩展（推荐）
```powershell
python scripts/build_fd_boost.py
```

### 3）运行标准验收算例
```powershell
python scripts/run_acceptance_case.py --mode all --backend boost_parallel --threads 14 --output-mode stream_to_disk --output-subdir forward_case_telefd2d --progress-step 200 --progress-sec 0.5
```

### 4）运行 PML 加厚 2 倍展示算例
```powershell
python scripts/run_acceptance_case.py --mode all --backend boost_parallel --threads 14 --output-mode stream_to_disk --output-subdir forward_case_telefd2d_pml2x --pml-x-scale 2 --pml-z-scale 2 --progress-step 200 --progress-sec 0.5
```

## MCP 集成（AI 可调用工作流）

telefd2d 现已提供 MCP 服务层，AI 代理可以通过结构化工具调用正演流程，而不必依赖脆弱的纯命令行拼接。

### 1）启动 MCP 服务
```powershell
python scripts/run_mcp_server.py
```

### 2）核心 MCP 工具
- `telefd2d_summarize_project`
- `telefd2d_run_forward_case`
- `telefd2d_get_case_report`
- `telefd2d_list_cases`

### 3）运行轻量 smoke 验证
```powershell
python scripts/mcp_smoke_test.py --backend baseline
```

### 4）MCP 文档
- 方案决策：`docs/mcp_decision.md`
- 接入指南与调用示例：`docs/mcp_integration.md`

## 仓库结构

- `src/fd_workflow/`：求解器、模型构建、后处理模块。
- `src/telefd2d_mcp/`：供 AI 调用的 MCP 适配层。
- `scripts/run_acceptance_case.py`：主流程入口。
- `scripts/run_mcp_server.py`：stdio MCP 服务入口。
- `scripts/mcp_smoke_test.py`：端到端轻量验证脚本。
- `scripts/benchmark_streaming.py`：内存/流式输出基准。
- `scripts/benchmark_speed_consistency.py`：速度与一致性基准。
- `assets/topo_demo/`：文档展示素材。
- `output/`：运行产物。
- `docs/`：流程记录与分析文档。

## 参考文献

1. Virieux, J. (1986). *P-SV wave propagation in heterogeneous media; velocity-stress finite-difference method*. Geophysics, 51(4), 889-901. https://doi.org/10.1190/1.1442147
2. Komatitsch, D., and Martin, R. (2007). *An unsplit convolutional perfectly matched layer improved at grazing incidence for the seismic wave equation*. Geophysics, 72(5), SM155-SM167. https://doi.org/10.1190/1.2757586
3. Cao, J., and Chen, J.-B. (2018). *A parameter-modified method for implementing surface topography in elastic-wave finite-difference modeling*. Geophysics, 83(6), T313-T332. https://doi.org/10.1190/GEO2018-0098.1

## 许可证

本项目采用 MIT 许可证，详见 `LICENSE`。
