# PML Tuning Report

Short-run tuning was executed before final full forward modeling.

- Backend: `boost_parallel`
- Threads: `16`
- Tune run nt: `1967`
- Grid: `751 x 244`
- Target domain (no PML): `100.0 km x 40.0 km`

## Candidates

| backend | threads | reflect_coeff | power | kappa_max | boundary_energy_ratio | runtime_s |
| --- | --- | --- | --- | --- | --- | --- |
| boost_parallel | 16 | 1.0e-06 | 2 | 1.00 | 5.631321e-01 | 1.16 |
| boost_parallel | 16 | 1.0e-07 | 2 | 1.00 | 5.635264e-01 | 1.20 |
| boost_parallel | 16 | 1.0e-07 | 2 | 1.30 | 5.784976e-01 | 1.18 |
| boost_parallel | 16 | 1.0e-08 | 3 | 1.30 | 6.338234e-01 | 1.29 |

## Final Choice

- `reflect_coeff=1.0e-06`
- `power=2`
- `kappa_max=1.00`
- Best boundary-energy ratio: `5.631321e-01`

This selected set can be passed into `scripts/run_acceptance_case.py` via:
- `--pml-reflect-coeff 1.0e-06`
- `--pml-power 2`
- `--pml-kappa-max 1.00`