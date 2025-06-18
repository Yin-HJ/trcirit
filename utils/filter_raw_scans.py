import os
import re
import click
import pandas as pd
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

def compress_scan_list(scan_list):
    """Compress the integer list into the format required by msconvert: such as [1,2,3,5,6] -> '[1,3] [5,6]'"""
    scan_list = sorted(set(scan_list))
    result = []
    i = 0
    while i < len(scan_list):
        start = scan_list[i]
        while i + 1 < len(scan_list) and scan_list[i + 1] == scan_list[i] + 1:
            i += 1
        end = scan_list[i]
        if start == end:
            result.append(f"{start}")
        else:
            result.append(f"[{start},{end}]")
        i += 1
    return " ".join(result)

def extract_and_save_scan_filters(msmsScan_path, output_dir, pep_thresh=0.01, score_thresh=0.7, chunksize=100000):
    """extract high-confidence scans and write to filter folder"""

    from collections import defaultdict

    scan_dict = defaultdict(list)
    use_cols = ["Raw file", "Scan number", "PEP", "Score", "Reverse"]
    total_rows = 0

    for chunk in pd.read_csv(msmsScan_path, sep='\t', usecols=use_cols, chunksize=chunksize):
        total_rows += len(chunk)
        mask = (
            (chunk["PEP"] <= pep_thresh) &
            (chunk["Score"] >= score_thresh) &
            (chunk["Reverse"].astype(str).str.strip() != "+")
        )
        scan_to_keep = chunk[~mask]
        for _, row in scan_to_keep.iterrows():
            raw = str(row["Raw file"]).strip()
            scan = int(row["Scan number"])
            scan_dict[raw].append(scan)

    os.makedirs(output_dir, exist_ok=True)
    summary = []

    for raw_file, scans in scan_dict.items():
        compressed = compress_scan_list(scans)
        raw_basename = os.path.splitext(os.path.basename(raw_file))[0]
        filter_txt_path = os.path.join(output_dir, f"{raw_basename}_scan2filter.txt")

        with open(filter_txt_path, "w") as f:
            f.write(f'filter="scanNumber {compressed}"\n')

        summary.append({"Raw file": raw_file, "Scan count": len(scans)})

    summary_path = os.path.join(output_dir, "scan_filter_summary.tsv")
    pd.DataFrame(summary).to_csv(summary_path, sep='\t', index=False)

    total_scans = sum(item["Scan count"] for item in summary)
    print(f"- [✓] Total scans retained for downstream: {total_scans}")
    print(f"- [✓] Total high-confidence scans excluded: {total_rows - total_scans}")
    print(f"- [✓] Written scan filters to: {output_dir}")
    print(f"- [✓] Summary saved to: {summary_path}")

    return 

def parse_compressed_scan_string(compressed):
    """
    Convert compressed scan string into list of scan numbers.
    Example: '[1,3] [5,6] 8' → [1, 2, 3, 5, 6, 8]
    """
    scans = []
    tokens = compressed.strip().split()
    for token in tokens:
        if token.startswith("[") and token.endswith("]"):
            start, end = token[1:-1].split(",")
            scans.extend(range(int(start), int(end) + 1))
        else:
            scans.append(int(token))
    return scans

def load_scan_filter_file(filter_dir):
    """
    Load per-sample scan filter files from the specified directory.

    Each file should be named as {sample_name}_scan2filter.txt and contain a single line:
        filter="scanNumber {compressed}"

    Returns:
        dict: mapping from sample_name to (filter_file_path, scan_count)
    """
    scan_map = {}

    for fname in os.listdir(filter_dir):
        if fname.endswith("_scan2filter.txt"):
            sample_name = re.sub(r"_scan2filter\.txt$", "", fname)
            full_path = os.path.join(filter_dir, fname)

            try:
                with open(full_path) as f:
                    line = f.readline().strip()

                # Extract the compressed scan string inside the quotes
                match = re.search(r'filter\s*=\s*"scanNumber\s+(.+?)"', line)
                if not match:
                    raise ValueError(f"Invalid format in {fname}")

                compressed = match.group(1)
                scan_list = parse_compressed_scan_string(compressed)
                scan_count = len(scan_list)

                scan_map[sample_name] = (full_path, scan_count)

            except Exception as e:
                print(f"[WARN] Failed to parse {fname}: {e}")
                scan_map[sample_name] = (full_path, -1)
    return scan_map

def build_msconvert_cmd(pwiz_path, input_path, filter_file_path, output_path):
    """Build msconvert cmd"""
    if not os.path.exists(filter_file_path):
        raise FileNotFoundError(f"Scan filter file not found: {filter_file_path}")

    cmd = [
        pwiz_path,
        input_path,
        "--mzML",
        "-c", filter_file_path,
        "--outdir", os.path.dirname(output_path),
        "--outfile", os.path.basename(output_path),
    ]

    return cmd

def run_filter_one_and_convert(pwiz_path, raw_dir, output_dir, raw_file, scan_filter_dir, scan_count=0, fileconverter_cmd="FileConverter", trfp_path="ThermoRawFileParser.exe",mono_cmd="mono", logger=None):
    
    """
    For each sample:
    1 .raw -> .mzML (trfp)
    2 .mzML -> filtered .mzML (msconvert)
    3 filtered .mzML -> .mzXML (FileConvert)
    """
    if logger is None:
        import logging
        logger = logging.getLogger("validate")

   
    raw_basename = os.path.splitext(raw_file)[0]  # 去掉 .mzML 后缀

    # Step 1: raw to mzML
    raw_file_raw = os.path.join(raw_dir, raw_basename + ".raw")
    mzml_from_raw = os.path.join(raw_dir, raw_file)

    cmd_trfp = [
    mono_cmd, trfp_path,
    "-i", raw_file_raw,
    "-b", mzml_from_raw,
    "-f", "2"
    ]

    logger.info(f"[CMD] ThermoRawFileParser: {' '.join(cmd_trfp)}")

    try:

        result = subprocess.Popen(
            cmd_trfp,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Read output stream in real time
        for line in result.stdout:
            line = line.rstrip()
            if line:
                logger.info(line)

        return_code = result.wait()
        if return_code == 0:
            print(f"- [✓] Raw file conversion done: {raw_basename}.raw → .mzML")
        
        else:
            msg = f"[✗] ThermoRawFileParser failed with code {return_code}: {raw_file_raw}"
            logger.error(msg)
            print(msg)
            raise RuntimeError(f"ThermoRawFileParser failed for {raw_basename}")

    except Exception  as e:
        logger.exception(f"[✗] Failed to launch ThermoRawFileParser: {e}")
        raise click.Abort()
    
    # Step 2: filter by msconverts
    input_path = mzml_from_raw
    output_file = raw_basename + "_filtered.mzML"
    output_path = os.path.join(output_dir, output_file)
    filter_file_path = os.path.join(scan_filter_dir, f"{raw_basename}_scan2filter.txt")

    cmd = build_msconvert_cmd(pwiz_path, input_path, filter_file_path, output_path)
    logger.info(f"msconvert start processing file: {raw_file}")
    logger.info(f"[CMD] msconvert: {' '.join(cmd)}")

    try:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        
        process = subprocess.Popen(
            cmd,
            env=env,
            # stdout=subprocess.PIPE, # too long msg occurs OSError
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        return_code = process.wait()

        if return_code == 0:
            print(f"- [✓] Filter successfully, extract {scan_count} scans from {raw_file}")
        else:
            msg = f"[✗] msconvert failed with code {return_code}: {raw_file}"
            logger.error(msg)
            print(msg)
            raise RuntimeError(f"msconvert failed for {raw_file}")
            
    except Exception  as e:
        logger.exception(f"[✗] Msconvert failed: {e}")
        raise click.Abort()

    # Step 3: Convert mzML to mzXML 
    mzxml_output = os.path.splitext(output_path)[0] + ".mzXML"
    mzxml_name = os.path.basename(mzxml_output)

    cmd_convert = [
        fileconverter_cmd,
        "-in", output_path,
        "-out", mzxml_output,
        "-force_MaxQuant_compatibility"
    ]
    logger.info(f"[CMD] FileConverter: {' '.join(cmd_convert)}")

    try:

        result_fc = subprocess.Popen(
            cmd_convert,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Read output stream in real time
        for line in result_fc.stdout:
            line = line.rstrip()
            if line:
                logger.info(line)
        return_code = result_fc.wait()
        if return_code == 0:
            print(f"- [✓] FileConverter completed: .mzML → {mzxml_name}")
        else:
            msg = f"[✗] FileConverter failed with code {return_code}: {mzxml_name}"
            logger.error(msg)
            print(msg)
            raise RuntimeError(f"FileConverter failed for {mzxml_name}")

    except Exception  as e:
        logger.exception(f"[✗] Failed to launch FileConverter: {e}")
        raise click.Abort()
    
def batch_filter_scans(raw_dir, filter_file, output_dir, pwiz_path="msconvert", mono_cmd="mono",fileconverter_cmd="FileConverter", trfp_path="ThermoRawFileParser.exe", threads=4, logger=None):
        """excuate run_filter_one_and_convert batchly"""
    
    if logger is None:
        import logging
        logger = logging.getLogger("validate")
    
    os.makedirs(output_dir, exist_ok=True)
    scan_map = load_scan_filter_file(filter_file)

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = []
        for raw_file_base, (filter_txt_path, scan_count) in scan_map.items():
            raw_file = raw_file_base + ".mzML"
            
            futures.append(
                executor.submit(
                    run_filter_one_and_convert,
                    pwiz_path=pwiz_path,
                    raw_dir=raw_dir,
                    output_dir=output_dir,
                    raw_file=raw_file,
                    scan_filter_dir=os.path.dirname(filter_txt_path),
                    mono_cmd=mono_cmd,
                    fileconverter_cmd=fileconverter_cmd,
                    trfp_path=trfp_path,
                    logger=logger,
                    scan_count = scan_count
                )
            )
        
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                logger.error(f"[✗] Thread failed with error: {e}")