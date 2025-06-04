import os
import click
import time
import shutil
import subprocess
import logging
import textwrap
from pathlib import Path
from utils import init_logger, check_java_environment

# trcirit identify -i tests/data/input/transcript-150.fa -w 10 -r data/genome/chm13.bed -g data/genome/chm13.fasta -D data/genome/build/chm13 -d chm13 -o tests/ident_out/ -p prefix

def add_identify_commands(cli):
    @cli.command(name="identify", help="""Identify, re-construct and annotate the full-length circRNAs. 

                Example: trcirit identify -i transcript-150.fa -w 10 -r chm13.bed -g chm13.fasta -D genome/build/chm13 -d chm13 -o ident_out/ -p prefix
                """,
                context_settings={'help_option_names': ['-h', '--help']})
    @click.option("--input", "-i", required=True, type=click.Path(exists=True), 
                help="Input FASTA file")
    @click.option("--prefix", "-p", default= None, type=str,
                help="Prefix for output files, defaut: prefix of input file")
    @click.option("--out_dir","-o", default="ident_out",
                help="Output directory, default: ident_out",
                type=click.Path(file_okay=False, dir_okay=True, writable=True, resolve_path=True))
    @click.option("--window", "-w", type=int, default=10,
                help="Window/seed (integer), initial search for CIRIT. default: 10")
    @click.option("--genome-ref", "-r", required=True, type=click.Path(exists=True, dir_okay=False, readable=True), 
                help="Genome reference (BED)")
    @click.option("--genome-seq", "-g", required=True, type=click.Path(exists=True, dir_okay=False, readable=True),
                help="Genome sequence (FASTA)")
    @click.option("--genome-index", '-d',required=True, type= str,
                help="Genome database name, created by gmap_build -d option")
    @click.option("--genome-dir", "-D", required=True, type= click.Path(exists=True, file_okay=False, readable=True),
                help="Genome directory, created by gmap_build -D option")                          
    @click.option("--java-path", type=click.Path(exists=True, executable=True, path_type=Path),
            help="Custom path to Java executable. default: auto-detect from PATH")

    def cmd_identify(input, window, prefix, genome_index, genome_dir, genome_seq, genome_ref, out_dir, java_path):

        # example: trcirit identify -i tests/data/input/transcript-150.fa -w 10 -r data/genome/chm13.bed -g data/genome/chm13.fasta -D data/genome/build/chm13 -d chm13

        # Initialize logger at module import
        logger = init_logger("identify")

        total_start = time.time()

        # implementation
        try:
            # 1. Check java version
            check_java_environment(java_path=java_path)

            # 2. Path preparation
            if prefix is None:
                prefix = Path(input).stem

            Path(out_dir).mkdir(parents=True, exist_ok=True)
            cirit_output = str(Path(out_dir) / f"{prefix}_circRNA_cirit.fa")
            trCIRIT_BSJ_output = str(Path(out_dir) / f"{prefix}_trCIRIT_full-length.fa")

            click.echo(f"================Starting identify module=================")
            click.secho(f"{input} is processing...")
            click.echo(f"Step1: circRNA identification")
            run_cirit(input, out_dir, window, java_path, prefix, logger)
            click.secho(f"Results saved to {cirit_output}\n", fg="red", bold=True)

            click.echo(f"Step2: re-construction of full-length circRNA")
            run_reconstruct(genome_index, genome_dir, genome_seq, genome_ref, java_path, out_dir, prefix, logger)
            
            click.secho(f"Results saved to {trCIRIT_BSJ_output}\n", fg="red", bold=True)
            click.echo(f"=========================JOB DONE========================") 
            logger.info(f"Results saved to {out_dir}!")
            click.echo(f"For more details on how the program is executed, see trcirit_identify.log!")
            
            write_summary(out_dir)
            total_time = time.time() - total_start
            click.secho(f"Pipeline completed in {total_time:.2f} seconds.", fg='green')

        except Exception as e:
            click.secho(f"Error: {e}", fg='red', err=True)
            raise click.Abort()
        
    return cli

def run_cirit(input, out_dir, window, java_path, prefix, logger):
    """Execute Java tool (cirit.jar) for circRNA identification
    
    Args:
        input_path (str): Input file path
        output_dir (str): Output directory
        window (int): Window/seed to initial search
        java_path: Custom path to Java executable (None for auto-detect)
        prefix: prefix of output files
        logger: logger to write log

    Returns:
        str: Path to generated results
        
    Raises:
        RuntimeError: If Java execution fails
    """
    # Example:
    # java -jar pkgs/Cirit-1.0.jar -i tests/data/input/transcript-150.fa -o test/ -w 10

    start_time = time.time()
    logger.info(f"Starting: input={input}, output_dir={out_dir}, window={window}, prefix={prefix}")

    try:

        # 1. Path preparation
        jar_path = str(Path(__file__).parent.parent / "pkgs" / "Cirit-1.0.jar")
        resolved_java = java_path if java_path else shutil.which("java")

        if not resolved_java:
            raise RuntimeError("Java not found and no --java-path specified")

        # 2. Build command 
        cmd = [
            resolved_java,
            "-jar",
            jar_path,
            "-i", str(input),
            "-o", str(Path(out_dir) / f"{prefix}_circRNAs_cirit.fa"),
            "-w", str(window)
        ]
        logger.info(f"Command: {' '.join(map(str, cmd))}")

        # 3. Run command 
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='UTF-8'
        )

        logger.info(f"Identify output:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}\n")
        logger.info(f"Identification completed in {time.time()-start_time:.2f}s\n")

    except Exception as e:
        logger.error(
            f"Identification failed: {str(e)}\n"
            f"Identification failed after {time.time()-start_time:.2f}s",
            exc_info=True
        )
        raise RuntimeError(f"Analysis failed: {str(e)}") from e

def run_reconstruct(genome_index, genome_dir, genome_seq, genome_ref, java_path, out_dir, prefix, logger):
    """Execute Java tool (trCIRIT-BSJ.jar) for circRNA full-length re-construction

    Args:
        genome_index: Genome database name
        genome_dir: Genome directory
        genome_seq: Genome sequence
        genome_ref: Genome reference
        output_dir (str): Output directory
        java_path: Custom path to Java executable (None for auto-detect)
        prefix = prefix of output files
        logger: logger to write log

    Returns:
        str: Path to generated results
        
    Raises:
        RuntimeError: If Java execution fails

    """
    # example:
    # java -jar pkgs/trCIRIT-BSJ-1.0.2.jar -s tests/ident_out/cirit_circRNA.fa -r data/genome/chm13.bed -g data/genome/chm13.fasta -D data/genome/build/chm13 -d chm13 [-o tests/BSJ_out -p prefix]
    
    step_start = time.time()
    logger.info(f"Starting: genome_index={genome_index}, genome_dir={genome_dir}, genome_seq={genome_seq}, genome_ref={genome_ref}, output_dir={out_dir}, prefix={prefix}")

    try:

    # 1. Path preparation
        out_dir = out_dir or "ident_out"
        input = Path(out_dir)/f"{prefix}_circRNAs_cirit.fa"
        jar_path = str(Path(__file__).parent.parent / "pkgs" / "trCIRIT-BSJ-1.0.2.jar")
        resolved_java = java_path if java_path else shutil.which("java")

        if not resolved_java:
            raise RuntimeError("Java not found and no --java-path specified")

        # 2. Build command 
        cmd = [
            resolved_java,
            "-jar",
            jar_path,
            "-s", str(input),
            "-d", str(genome_index),
            "-D", str(Path(genome_dir)),
            "-g", str(Path(genome_seq)),
            "-r", str(Path(genome_ref)),
            "-p", str(prefix),
            "-o", str(Path(out_dir))
        ]
        logger.info(f"Command: {' '.join(map(str, cmd))}")

        # 3. Run command 
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='UTF-8'
        )
            
        logger.info(f"Re-construct full-length output:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}\n")
        # logger.info(f"Re-construct completed in {time.time()-step_start:.2f}s\n")

    except Exception as e:
        logger.error(
            f"Identification failed: {str(e)}\n",
            # f"Reconstruction failed after {time.time()-step_start:.2f}s",
            exc_info=True
        )
        raise RuntimeError(f"Analysis failed: {str(e)}") from e

def write_summary(out_dir):
    """ Write a README.md in output directory.
    """
    readme_path = Path(out_dir) / "README.md"
    readme_content =textwrap.dedent("""\
    # Output Summary

    This directory contains the following files generated by trcirit identify module:

    - `{prefix}_circRNAs_cirit.fa`: circRNA sequence generated by CIRIT.
    - `{prefix}_trCIRIT_full-length.fa`: Re-constructed full-length sequence of circRNAs.
    - `{prefix}_trCIRIT_anno.gtf`: Annotation file for full-length circRNAs.
    - `{prefix}_gmap.out`: Log file produced by gmap.
    """)

    with open(readme_path, "w") as f:
        f.write(readme_content)

