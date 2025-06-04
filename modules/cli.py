import click
from modules.identify import add_identify_commands
from modules.build import add_build_commands
from modules.validate import add_validate_commands
from modules.analyze import add_analyze_commands
from modules.tools import add_tools_commands
from importlib.metadata import version, PackageNotFoundError

# get version from toml 
try:
    __version__ = version("trcirit")
except PackageNotFoundError:
    __version__ = "unknown"

# custom class for grouping output 
class CustomCLI(click.Group):
    def __init__(self, *args, help_width=120, **kwargs):
        super().__init__(*args, **kwargs)
        self.help_width = help_width  # Allow setting help width dynamically

    def format_commands(self, ctx, _formatter):
        formatter = click.HelpFormatter(width=self.help_width)

        main_cmds = {}
        tool_cmds = {}
        for name, cmd in self.commands.items():
            if getattr(cmd, 'is_tool', False):
                tool_cmds[name] = cmd
            else:
                main_cmds[name] = cmd

        _formatter.write('\n')

        if main_cmds:
            with formatter.section('Main Modules'):
                self._write_command_section(ctx, formatter, main_cmds)

        if tool_cmds:
            with formatter.section('Tools'):
                self._write_command_section(ctx, formatter, tool_cmds)

        # Write formatted help to the original formatter's output stream
        _formatter.write(formatter.getvalue())

    def _write_command_section(self, ctx, formatter, commands):
        rows = []
        for subcommand in sorted(commands):
            cmd = self.get_command(ctx, subcommand)
            if not cmd or not cmd.help:
                help_str = ""
            else:
                help_lines = cmd.help.strip().splitlines()
                first_line = ""
                for line in help_lines:
                    line = line.strip()
                    if line:
                        first_line = line
                        break
                max_len = self.help_width
                if len(first_line) > max_len:
                    first_line = first_line[:max_len-3] + "..."
                help_str = first_line
            rows.append((subcommand, help_str))
        if rows:
            formatter.write_dl(rows)

@click.group(cls=CustomCLI, help_width=120,
    context_settings={
    'help_option_names': ['-h', '--help'],
    'max_content_width': 100
    })
@click.version_option(__version__, '-v', '--version', message='trcirit version: %(version)s')
def cli():
    """A bioinformatics tool for backward translation identification and validation."""
    pass

# Register all module commands with the main CLI group
cli = add_identify_commands(cli)
cli = add_build_commands(cli)
cli = add_validate_commands(cli)
cli = add_analyze_commands(cli)

cli = add_tools_commands(cli)

# Entry point when executed directly
if __name__ == "__main__":
    cli()



