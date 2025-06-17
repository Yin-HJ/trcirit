import os
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

def extract_high_conf_scans_and_convert(msmsScan_path, output_path, pep_thresh=0.01, score_thresh=0.7, chunksize=100000):
    """
    Read msmsScans in blocks, extract high-confidence scans, and finally generate scan tables to be filtered out.
    """
    scan_dict = defaultdict(list)
    use_cols = ["Raw file", "Scan number", "PEP", "Score", "Reverse"]

    for chunk in pd.read_csv(msmsScan_path, sep='\t', usecols=use_cols, chunksize=chunksize):
        
        #Filter high-quality rows (those to be filtered out)
        mask = (
            (chunk["PEP"] <= pep_thresh) &
            (chunk["Score"] >= score_thresh) &
            (chunk["Reverse"].astype(str).str.strip() != "+")
        )

        # !!Because the filter parameter of msconvert is followed by the spec ID to be reserved, it needs to be reversed here.
        high_conf = chunk[~mask]

        for _, row in high_conf.iterrows():
            raw = str(row["Raw file"]).strip()
            scan = int(row["Scan number"])
            scan_dict[raw].append(scan)

    # formatted
    result = []
    for raw_file, scans in scan_dict.items():
        compressed = compress_scan_list(scans)
        result.append({"Raw file": raw_file, "Scan ranges": compressed, "Scan count": len(scans)})

    pd.DataFrame(result).to_csv(output_path, sep='\t', index=False)
    total = sum(len(scans) for scans in scan_dict.values())
    print(f"- [✓] Extracted {total} high-confidence mRNA scans and will be filtered subsequently.")
    print(f"- Result table saved to {output_path}")
    return total


# filter scans from each raw file
def load_scan_filter_file(filter_file):
    df = pd.read_csv(filter_file, sep='\t')
    return {row["Raw file"]: (row["Scan ranges"], int(row.get("Scan count", -1))) for _, row in df.iterrows()}

def build_msconvert_cmd(pwiz_path, input_path, scan_filter, output_path):
    return [
        pwiz_path,
        input_path,
        "--mzML",
        f'--filter', f'scanNumber {scan_filter}',
        "--outdir", os.path.dirname(output_path),
        "--outfile", os.path.basename(output_path),
    ]

def run_filter_one_and_convert(pwiz_path, raw_dir, output_dir, raw_file, scan_filter, scan_count=0, fileconverter_cmd="FileConverter", trfp_path="ThermoRawFileParser.exe",mono_cmd="mono", logger=None):
    
    """
    For each sample:
    1 .raw -> .mzML (trfp)
    2 .mzML -> filtered .mzML (msconvert)
    3 filtered .mzML -> .mzXML (FileConvert)
    """
    if logger is None:
        import logging
        logger = logging.getLogger("validate")

    # Step 1: raw to mzML
    raw_basename = os.path.splitext(raw_file)[0]  # 去掉 .mzML 后缀
    raw_file_input = os.path.join(raw_dir, raw_basename + ".raw")
    mzml_from_raw = os.path.join(raw_dir, raw_file)

    cmd_trfp = [
    mono_cmd, trfp_path,
    "-i", raw_file_input,
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
            msg = f"[✗] ThermoRawFileParser failed with code {return_code}: {raw_file_input}"
            logger.error(msg)
            print(msg)
            raise RuntimeError(f"ThermoRawFileParser failed for {raw_basename}")

    except Exception  as e:
        # print(f"[✗] Failed to start ThermoRawFileParser for {raw_file_input}")
        logger.exception(f"[✗] Failed to launch ThermoRawFileParser: {e}")
        raise click.Abort()
    
    # Step 2: filter by msconverts
    input_path = os.path.join(raw_dir, raw_file)
    output_file = os.path.splitext(raw_file)[0] + "_filtered.mzML"
    output_path = os.path.join(output_dir, output_file)

    cmd = build_msconvert_cmd(pwiz_path, input_path, scan_filter, output_path)
    logger.info(f"[CMD] msconvert: {' '.join(cmd)}")

    try:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Read output stream in real time
        for line in process.stdout:
            line = line.rstrip()
            if line:
                # print(line)
                logger.info(line)

        return_code = process.wait()

        if return_code == 0:
            print(f"- [✓] Filter successfully, filtered {scan_count} scans from {raw_file}")
        else:
            msg = f"[✗] msconvert failed with code {return_code}: {raw_file}"
            logger.error(msg)
            print(msg)
            raise RuntimeError(f"msconvert failed for {raw_file}")
            
    except Exception  as e:
        # print(f"[✗] Failed to start msconvert for {raw_file}")
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
        # print(f"[✗] Failed to start FileConverter for {mzxml_name}")
        logger.exception(f"[✗] Failed to launch FileConverter: {e}")
        raise click.Abort()
    
def batch_filter_scans(raw_dir, filter_file, output_dir, pwiz_path="msconvert", mono_cmd="mono",fileconverter_cmd="FileConverter", trfp_path="ThermoRawFileParser.exe", threads=4, logger=None):
    
    if logger is None:
        import logging
        logger = logging.getLogger("validate")
    
    os.makedirs(output_dir, exist_ok=True)
    scan_map = load_scan_filter_file(filter_file)

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = []
        for raw_file_base, (scan_filter, scan_count) in scan_map.items():
            raw_file = raw_file_base + ".mzML"
            
            futures.append(
                executor.submit(
                    run_filter_one_and_convert,
                    pwiz_path=pwiz_path,
                    raw_dir=raw_dir,
                    output_dir=output_dir,
                    raw_file=raw_file,
                    scan_filter=scan_filter,
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