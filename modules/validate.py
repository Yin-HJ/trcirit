import os
import click
import time
import yaml
import subprocess
from pathlib import Path
from utils import init_logger
from utils.generate_xml import generate_mqpar
from utils.filter_raw_scans import (
    extract_and_save_scan_filters,
    batch_filter_scans
)

def add_validate_commands(cli):
    @cli.command(name="validate", help="""Validate circRNA-derived peptides via a two-round MaxQuant search.

                1) Search raw files against linear mRNA reference;
                2) Extract high-confidence spectra;
                3) Remove matched spectra from raw files;
                4) Re-search against circRNA-derived peptide reference.

                Example: trcirit validate -f config.yaml
                """,
                context_settings={'help_option_names': ['-h', '--help']})
    @click.option("--config", "-f", required=True, type=click.Path(exists=True), 
                help="YAML config file for pipeline")
    @click.option("--out_dir","-o", default="valid_out",
                help="Output directory, default: valid_out",
                type=click.Path(file_okay=False, dir_okay=True, writable=True, resolve_path=True))
    @click.option("--dryrun", "-d", is_flag=True, default=False,
              help="Dry run mode: only generate mqpar.xml and print commands without execution")
    @click.option("--skip-generate", "-s", is_flag=True, default=False,
              help="Skip generating mqpar.xml files (if manually modified after --dryrun)")

    def cmd_validate(config, out_dir, dryrun, skip_generate):

        logger = init_logger("validate")
        total_start = time.time()

        try:
            
            if dryrun and skip_generate:
                click.secho("[Error] --dryrun and --skip-generate cannot be used together.", fg="red", err=True)
                click.secho("Use --dryrun to generate mqpar.xml files and view commands.", fg="yellow", err=True)
                click.secho("Use --skip-generate only when mqpar.xml files are manually prepared.", fg="yellow", err=True)
                raise click.Abort()

            if dryrun:
                click.secho("\nDryrun mode enabled: No actual computation will be performed.\n", fg="yellow")

            click.secho("Tips: Go to trcirit_validate.log check detailed progress!", fg="blue")
            click.echo("Parsing loaded parameters... ")
            cfg, out_dir_path = load_config(config, out_dir)

            # === Step 1 ===
            click.echo("\nStep1: Starting MaxQuant analysis for linear mRNA reference (time consuming) ... ")
            logger.info("=== Start Step1 ===")
            logger.info("Tips: Go to rawFilePath/combined/proc to check MaxQuant progress!")

            mqpar_linear = os.path.join(out_dir_path, "mqpar_linear.xml")
            if skip_generate:
                ensure_mqpar_exists(mqpar_linear, "linear reference")
            else:
                generate_mqpar(cfg=cfg, output_path=out_dir_path, fasta_key="fastaFilePath_linear", raw_subdir=None, suffix="_linear")
            
            if dryrun:
                click.echo(f"[Dryrun] Would run MaxQuant: dotnet {cfg['mq_cmd']} {mqpar_linear}")
            else:
                run_maxquant(cfg["mq_cmd"], mqpar_linear, "linear", logger)
                # click.echo(f"Test: run MaxQuant: dotnet {cfg['mq_cmd']} {mqpar_linear}")

            # === Step 2 ===
            click.echo("\nStep2: Extracting high-confidence linear mRNA scans...")
            logger.info("=== Start Step2 ===")
            msmsScan_path = os.path.join(cfg["rawFilePath"], "combined/txt/msmsScans.txt")
            scan_filter_dir = os.path.join(out_dir_path, "scan_filter")

            if dryrun:
                click.echo(f"[Dryrun] Would extract high-confidence scans from {msmsScan_path} to {scan_filter_dir}")
            else:
                extract_and_save_scan_filters(
                    msmsScan_path=msmsScan_path,
                    output_dir=scan_filter_dir,
                    pep_thresh=cfg.get("pep_thresh", 0.01),
                    score_thresh=cfg.get("score_thresh", 0.7)
                )
                logger.info("Extract high-confidence scan numbers successfully!")

            # === Step 3 ===
            click.echo("\nStep3: Spectra filtering and raw files converting (time consuming)...")
            logger.info("=== Start Step3 ===")
            filtered_raw_dir = os.path.join(out_dir_path, "linear_free")

            if dryrun:
                click.echo(f"[Dryrun] Would filter spectra in {cfg['rawFilePath']} using files in {scan_filter_dir}, output to {filtered_raw_dir}")
            else:
                batch_filter_scans(
                    raw_dir=cfg["rawFilePath"],
                    filter_file=scan_filter_dir,
                    output_dir=filtered_raw_dir,
                    pwiz_path=cfg["pwiz_path"],
                    trfp_path=cfg["trfp"],
                    threads=cfg["threads"],
                    logger=logger,
                    mono_cmd=cfg.get("mono", "mono"),
                    fileconverter_cmd=cfg.get("fileconverter", "FileConverter")
                )
            # === Step 4 ===
            click.echo("\nStep4: Starting MaxQuant analysis for circular mRNA reference (time consuming)... ")
            logger.info("=== Start Step4 ===")

            mqpar_circ = os.path.join(out_dir_path, "mqpar_circ.xml")
            if skip_generate:
                ensure_mqpar_exists(mqpar_circ, "circRNA reference")
            else:
                generate_mqpar(cfg=cfg, output_path=out_dir_path, fasta_key="fastaFilePath_circ", raw_subdir="linear_free", suffix="_circ")
            
            if dryrun:
                click.echo(f"[Dryrun] Would run MaxQuant: dotnet {cfg['mq_cmd']} {mqpar_circ}")
            else:
                run_maxquant(cfg["mq_cmd"], mqpar_circ, "circular", logger)
                click.secho(f"- Raw outputs saved to {os.path.relpath(out_dir)}/linear_free/combined/.")
            
            if dryrun:
                mqpar_paths = [
                    os.path.join(out_dir_path, "mqpar_linear.xml"),
                    os.path.join(out_dir_path, "mqpar_circ.xml")
                ]
                click.secho("\n[Dryrun] Generated mqpar.xml files:", fg='cyan')
                for path in mqpar_paths:
                    click.secho(f" - {path}", fg='cyan')
                logger.info("Dryrun completed. mqpar.xml files generated.")
            else:
                total_time = time.time() - total_start
                time_str = format_duration(total_time)
                click.secho(f"\nPipeline completed in {time_str}.", fg='green')
                click.secho(f"Results saved to {out_dir_path}.", fg='green')
                logger.info(f"Results saved to {out_dir_path}.")
        
        except Exception as e:
            click.secho(f"Error: {e}", fg='red', err=True)
            logger.exception("Pipeline failed")
            raise click.Abort() 
    return cli

# === Utility Functions ===
def load_config(config_path, out_dir_path):

    config_path = Path(config_path).resolve()
    out_dir = Path(out_dir_path).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        with config_path.open() as f:
            raw_cfg = yaml.safe_load(f)
    except Exception as e:
        raise RuntimeError(f"[✗] Failed to load config file: {config_path}\n{e}")

    required = raw_cfg.get("Required", {})
    defaults = raw_cfg.get("Defaults", {})
    recommended = raw_cfg.get("Recommended", {})

    required_keys = ["template", "exp_design",  "rawFilePath", "fastaFilePath_linear", "fastaFilePath_circ"]
    missing = [k for k in required_keys if k not in required]
    if missing:
        raise ValueError(f"[✗] Missing required config keys: {missing}")

    merged = {**defaults, **required, **recommended}

    # translate relative path to absolute path 
    path_keys = [
        "mq_cmd", "pwiz_path", "trfp", "template", "rawFilePath", "exp_design", "fastaFilePath_linear", "fastaFilePath_circ"
    ]

    not_exist = []
    for key in path_keys:
        if key in merged:
            abs_path = Path(merged[key]).expanduser().resolve()
            merged[key] = str(abs_path)
            if not abs_path.exists():
                not_exist.append(f"{key}: {abs_path}")

    if not_exist:
        msg = "[✗] The following paths do not exist:\n" + "\n".join(not_exist)
        raise FileNotFoundError(msg)

    return merged, out_dir

def run_maxquant(mq_cmd, mqpar_xml, ref_type, logger):
    """Run MaxQuant command-line with given mqpar.xml
        Args:
        mq_cmd (str or Path): Path to MaxQuantCmd.exe
        mqpar_xml (str or Path): Path to mqpar.xml
        ref_type (str): Reference type (e.g., 'linear' or 'circRNA')
    """
    cmd = ["dotnet", mq_cmd, mqpar_xml]
    logger.info(f"[CMD] Running MaxQuant: {' '.join(cmd)}")

    try:

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # Read output stream in real time
        for line in process.stdout:
            line = line.rstrip()
            if line:
                try:
                    click.echo(f"- {line}") 
                except OSError:
                    pass
                logger.info(line)

        return_code = process.wait()
        if return_code == 0:
            click.echo(f"- [✓] MaxQuant finished successfully for {ref_type} reference.")
        else:
            msg = f"[✗] MaxQuant exited with code {return_code}"
            logger.error(msg)
            click.secho(msg, fg='red', err=True)
            raise click.Abort()

    except Exception as e:
        logger.exception(f"[✗] Unexpected failure during MaxQuant run for {ref_type}")
        # click.secho(f"[✗] MaxQuant failed unexpectedly for {ref_type} reference.", fg='red', err=True)
        raise click.Abort()

def format_duration(seconds):
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    
    return ' '.join(parts)

def print_cmd(cmd_list, logger):
    cmd_str = ' '.join(str(c) for c in cmd_list)
    logger.info(f"[Dryrun CMD] {cmd_str}")
    click.secho(f"[Dryrun CMD] {cmd_str}", fg='yellow')

def ensure_mqpar_exists(path, label):
    if not os.path.exists(path):
        click.secho(f"[Error] --skip-generate specified, but required mqpar.xml for {label} not found:\n  {path}", fg="red", err=True)
        click.secho(f"Suggestion: Run with --dryrun first to generate this file.", fg="yellow", err=True)
        raise click.Abort()
    click.echo(f"[Skip] Skipping mqpar.xml generation for {label}.")