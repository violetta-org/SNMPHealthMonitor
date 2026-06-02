---
trigger: always_on
description: Project specific rules for SNMPHealthMonitor
---
## Rules
1. **PowerShell Commands**:
   - Do NOT use the `&&` operator directly in terminal commands (PowerShell 5.1 does not support it).
   - Use `cmd /c "command1 && command2"` or run them sequentially using semicolons `;`.
   - When suggesting multi-line shell commands, use the backtick (`` ` ``) as the line continuation character for PowerShell (not backslash `\`).

2. **Python Environment**:
   - Always run Python scripts and pip installations inside the Conda environment named `python_programming`.
   - Prefix commands with `conda run -n python_programming`.

3. **Django & ASGI**:
   - Do NOT start background tasks or UDP listeners in `apps.py` AppConfig `ready()`.
   - All background services must be registered and managed under the ASGI `LifespanManager` in `asgi.py`.