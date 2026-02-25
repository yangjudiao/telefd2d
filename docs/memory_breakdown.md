# Memory Breakdown (Prompt_1)

## Grid and Case
- Domain (excluding PML): 100.0 km x 40.0 km
- Grid total: nx=751, nz=244, nt=5621

## Estimated Solver-Core Memory
- Runtime state (`vx`, `vz`, `tau*`, `memo*`): 0.018 GiB
- PM parameter arrays (`bx/bz/mu_xz/eta*`): 0.010 GiB

## Output Memory/Storage Footprint
- Snapshot files (`snap_vx/snap_vz/snap_it`): 0.164 GiB
- Seismogram files (`seismo_vx/seismo_vz`): 0.063 GiB
- Total output files: 0.227 GiB

## Measured Peak RSS
- In-memory mode peak RSS: 0.351 GiB
- Streaming mode peak RSS: 0.351 GiB
- Peak RSS reduction: 0.000 GiB

## Measured Peak USS
- In-memory mode peak USS: 0.325 GiB
- Streaming mode peak USS: 0.099 GiB
- Peak USS reduction: 0.227 GiB

## Conclusion
- Streaming mode moves output buffers to disk-backed files during runtime, reducing resident memory pressure.
