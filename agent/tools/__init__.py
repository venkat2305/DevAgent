"""Agent tools package.

Contains simple tool wrappers the agent brain can call.

Exposed tools:
- ShellTool: run shell commands via bash -lc
- FsTool: safe read/write/list under a base directory
- CodeExecTool: run small Python or Node snippets
- XdotTool: minimal xdotool wrapper (optional at this stage)
"""

from .shell import ShellTool  # noqa: F401
from .fs import FsTool  # noqa: F401
from .codeexec import CodeExecTool  # noqa: F401
from .xdot import XdotTool  # noqa: F401
