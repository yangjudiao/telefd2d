from __future__ import annotations

import warnings

from benchmark_speed_consistency import main


if __name__ == "__main__":
    warnings.warn(
        "scripts/benchmark_prompt2_speed.py is deprecated; use scripts/benchmark_speed_consistency.py",
        DeprecationWarning,
        stacklevel=1,
    )
    main()
