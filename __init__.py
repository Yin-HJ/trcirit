# Expose core interfaces at package level
# Allows importing directly from trcirit (e.g. 'from trcirit import cli')

from modules.cli import cli
from modules.identify import add_identify_commands
from modules.build import add_build_commands
from modules.validate import add_validate_commands
from modules.analyze import add_analyze_commands

__all__ = ["cli"]
