import click
from trcirit import identify, build, verify, analysis

@click.group()  # 定义一个命令组
def cli():
    """TRCRIT: A bioinformatics tool for bakward translation identification and verification."""
    pass

# 添加 identify 命令
@cli.command(name="identify")
@click.option("--input", "-i", required=True, help="Input file for identification.")
@click.option("--output", "-o", default="output.txt", help="Output file for results.")
def identify_cmd(input, output):
    """Run the identification module."""
    click.echo(f"Running identify on {input}...")
    identify.run(input, output)  # 调用 identify 模块的核心逻辑
    click.echo(f"Results saved to {output}.")

# 添加 build 命令
@cli.command(name="build")
@click.option("--input", "-i", required=True, help="Input file for building.")
@click.option("--output", "-o", default="output.txt", help="Output file for results.")
def build_cmd(input, output):
    """Run the build module."""
    click.echo(f"Running build on {input}...")
    build.run(input, output)  # 调用 build 模块的核心逻辑
    click.echo(f"Results saved to {output}.")

# 添加 verify 命令
@cli.command(name="verify")
@click.option("--input", "-i", required=True, help="Input file for verification.")
def verify_cmd(input):
    """Run the verification module."""
    click.echo(f"Running verify on {input}...")
    verify.run(input)  # 调用 verify 模块的核心逻辑
    click.echo("Verification complete.")

# 添加 analysis 命令
@cli.command(name="analysis")
@click.option("--input", "-i", required=True, help="Input file for analysis.")
@click.option("--output", "-o", default="analysis_results.txt", help="Output file for results.")
def analysis_cmd(input, output):
    """Run the analysis module."""
    click.echo(f"Running analysis on {input}...")
    analysis.run(input, output)  # 调用 analysis 模块的核心逻辑
    click.echo(f"Analysis results saved to {output}.")

# 主入口
if __name__ == "__main__":
    cli()