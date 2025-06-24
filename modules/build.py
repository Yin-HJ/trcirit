import os
import click
import time
import shutil
import subprocess
import logging
import textwrap
from pathlib import Path
from Bio import SeqIO
from Bio.Seq import Seq
from utils import init_logger, check_java_environment

# trcirit build -i tests/ident_out/transcript-150_trCIRIT_full-length.fa -o tests/build_out -p prefix

def add_build_commands(cli):
    @cli.command(name="build", help="""Find potential circRNA ORFs and build reference for MS search.

                Example: trcirit build -i trCIRIT_full-length.fa -o build_out -p prefix            
                """,
                context_settings={'help_option_names': ['-h', '--help']})
    @click.option("--input", "-i", required=True, type=click.Path(exists=True), 
                help="circRNA full-length sequence (FASTA)")
    @click.option("--prefix", "-p", default= None, type=str,
                help="Prefix for output files, defaut: prefix of input file")
    @click.option("--out_dir","-o", default="build_out",
                help="Output directory, default: build_out",
                type=click.Path(file_okay=False, dir_okay=True, writable=True))
    @click.option("--java-path", type=click.Path(exists=True, executable=True, path_type=Path),
            help="Custom path to Java executable. default: auto-detect from PATH")

    def cmd_build(input, out_dir, prefix, java_path):

        # Initialize logger at module import
        logger = init_logger("build")

        total_start = time.time()

        try:
             # 1. Check java version
            check_java_environment(java_path=java_path)

            # 2. Path preparation
            if prefix is None:
                prefix = Path(input).stem.split("_")[0] # "sample_name" > "sample" as prefix

            Path(out_dir).resolve().mkdir(parents=True, exist_ok=True)

            click.echo(f"================Starting build module=================")
            click.secho(f"{input} is processing...")
            click.echo(f"Step1: Find potential ORFs for circRNAs")
            run_build(input, out_dir, prefix, java_path ,logger)

            click.echo(f"\nStep2: Translate RNA sequences into protein sequences")
            run_translate(out_dir, logger) 
            click.secho(f"Results saved to {out_dir}\n", fg="red", bold=True)
            click.echo(f"======================JOB DONE========================") 
            logger.info(f"Results saved to {out_dir}!")
            click.echo(f"For more details on how the program is executed, see trcirit_build.log!")
            
            write_summary(out_dir)
            total_time = time.time() - total_start
            click.secho(f"Pipeline completed in {total_time:.2f} seconds.", fg='green')

        except Exception as e:
            click.secho(f"Error: {e}", fg='red', err=True)
            raise click.Abort()

    return cli

def run_build(input, out_dir, prefix, java_path, logger):
    """ Find potential ORFs from full-length circRNA

    Args:
        input (str): re-constrcted full-length circRNA
        out_dir (str): Output directory
        java_path: Custom path to Java executable (None for auto-detect)
        prefix: prefix of output files
        logger: logger to write log
    
    Returns:
        str: Path to generated results
        
    Raises:
        RuntimeError: If Java execution fails
    """

    # Exmaple:
    #  java -jar pkgs/trCIRIT-ORF-1.0.3.jar -s tests/ident_out/transcript-150_trCIRIT_full-length.fa -o tests/ORF_test -p prefix

    start_time = time.time()
    logger.info(f"Starting: input={input}, output_dir={out_dir}, prefix={prefix}")

    try:
        # 1. Path preparation
        out_dir = out_dir or "build_out"
        jar_path = str(Path(__file__).parent.parent / "pkgs" / "trCIRIT-ORF-1.0.3.jar")
        resolved_java = java_path if java_path else shutil.which("java")

        if not resolved_java:
            raise RuntimeError("Java not found and no --java-path specified")

        # 2. Build command
        cmd = [
            resolved_java,
            "-jar",
            jar_path,
            "-s", str(input),
            "-o", str(out_dir),
            "-p", str(prefix)
            
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
            
        logger.info(f"Find ORF output:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}\n")

    except Exception as e:
        logger.error(
            f"Find ORF failed: {str(e)}\n"
            f"Find ORF failed after {time.time()-start_time:.2f}s",
            exc_info=True
        )
        raise RuntimeError(f"Analysis failed: {str(e)}") from e

def run_translate(fa_dir, logger):
    """Batch translates all.fa or .fasta files in the specified directory into protein sequences.

    Args:
        fa_dir (str): input file path.
    """

    logger.info(f"Tranlate ORF to Protein output:\n")
    fa_dir = Path(fa_dir)
    assert fa_dir.is_dir(), f"Directory not exist: {fa_dir}"

    # Files whose names contain ".fa" and ". fasta" and do not contain "protein"
    fasta_files = [
        f for f in fa_dir.glob("*.fa") if "protein" not in f.stem and "trCIRIT" in f.stem
    ] + [
        f for f in fa_dir.glob("*.fasta") if "protein" not in f.stem and "trCIRIT" in f.stem
    ]


    if not fasta_files:
        click.echo(f"[Info] No .fa or .fasta files found in {fa_dir}")
        return

    for fa_file in fasta_files:
        output_file = fa_file.with_name(f"{fa_file.stem}_protein.fa")
        count = translate_orf(str(fa_file), str(output_file))
        click.echo(f"[✓] Translated {fa_file.name} → {output_file.name} ({count} proteins)")

        logger.info(f"[✓] Translated {fa_file.name} → {output_file.name} ({count} proteins)")


def translate_orf(circRNA_fasta_path: str, protein_fasta: str) -> int:
    """Translate ORF sequences into protein sequences (using standard codon tables)

    Args:
        orf_fasta_path (str): ORF sequence path (FASTA)
        output_protein_fasta (str): Protein sequence path (FASTA)

    Returns:
        int: Number of successfully translated sequences
    """
    orf_fasta_path = Path(circRNA_fasta_path)
    output_protein_fasta = Path(protein_fasta)
    count = 0

    with open(output_protein_fasta, "w") as out_handle:
        for record in SeqIO.parse(orf_fasta_path, "fasta"):
            rna_seq = record.seq

            # 翻译为蛋白质（到终止密码子）
            try:
                protein_seq = rna_seq.translate(to_stop=True)
                out_handle.write(f">{record.id}\n{protein_seq}\n")
                count += 1
            except Exception as e:
                print(f"[Warning] Failed to translate {record.id}: {e}")
    
    return count


def write_summary(out_dir):
    """ Write a README.md in output directory.
    """
    readme_path = Path(out_dir) / "README.md"
    readme_content =textwrap.dedent("""\
    # Output Summary

    This directory contains the following files generated by trcirit identify module:

    - `{prefix}_backward_trCIRIT_ORF.fa`: Potential ORFs from backward circRNAs(exclude circRNAs that spans BSJ).
    - `{prefix}_forward_trCIRIT_ORF.fa`: Potential ORFs from forward circRNAs(exclude circRNAs that spans BSJ).
    - `{prefix}_backward_trCIRIT_ORF-BSJ.fa`: Potential ORFs from backward circRNAs which spans BSJ.
    - `{prefix}_forward_trCIRIT_ORF-BSJ.fa`: Potential ORFs from forward circRNAs which spans BSJ.

    - `{prefix}_backward_trCIRIT_ORF_protein.fa`: Potential protein seq from backward circRNAs(exclude circRNAs that spans BSJ).
    - `{prefix}_forward_trCIRIT_ORF_protein.fa`: Potential protein seq from forward circRNAs(exclude circRNAs that spans BSJ).
    - `{prefix}_backward_trCIRIT_ORF-BSJ_protein.fa`: Potential protein seq from backward circRNAs which spans BSJ.
    - `{prefix}_forward_trCIRIT_ORF-BSJ_protein.fa`: Potential protein seq from forward circRNAs which spans BSJ.
    """)

    with open(readme_path, "w") as f:
        f.write(readme_content)