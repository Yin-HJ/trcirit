from lxml import etree as ET
from pathlib import Path
import pandas as pd
import yaml
import os

def generate_mqpar(cfg, output_path, fasta_key="fastaFilePath", raw_subdir=None, suffix=""):
    """
    Generate mqpar.xml based on provided configuration.

    Args:
        cfg (dict): merged configuration dictionary from load_config()
        output_path (str or Path): path to output mqpar.xml
        fasta_key (str): key in cfg that contains FASTA path
        raw_subdir (str or None): If provided, save linear-free files into it
        suffix (str): optional suffix to append to <name>
    """

    template_path = Path(cfg["template"]).resolve()
    exp_design_path = Path(cfg["exp_design"]).resolve()

    # read template and experimental design
    tree = ET.parse(template_path)
    root = tree.getroot()
    df = pd.read_csv(exp_design_path, sep='\t')

    # update parameters
    project_name = cfg.get("projectName", "default_name") + suffix
    root.find("name").text = project_name
    root.find("numThreads").text = str(cfg.get("threads", 4))
    root.find(".//fastaFilePath").text = cfg.get(fasta_key, "")

    # Optional(Recommended) search parameters from config
    optional_tags = {
        "enzymes": list,
        "fixedModifications": list,
        "variableModifications": list,
        "maxMissedCleavages": int,
        "firstSearchTol": float,
        "mainSearchTol": float,
        "minPeptideLength": int,
        "minRatioCount": int
    }

    list_tags = ["fixedModifications", "enzymes", "variableModifications"]
    for tag, caster in optional_tags.items():
       
        value = cfg.get(tag)
        if not value :
            continue

        elem = root.find(f".//{tag}")
        if elem is None:
            print(f"[WARN] Tag <{tag}> not found in template. Skipped.")
            continue

        if tag in list_tags:
            # Clear existing and write new
            for child in list(elem):
                elem.remove(child)
            if isinstance(value, str):
                value = [v.strip() for v in value.split(",")]
            elif not isinstance(value, list):
                raise ValueError(f"{tag} should be a list or comma-separated string.")
            for v in value:
                ET.SubElement(elem, "string").text = v
        else:
            elem.text = str(caster(value))

    # clear existing filePaths / experiments / fractions
    for tag in ["filePaths", "experiments", "fractions", "ptms", "paramGroupIndices", "referenceChannel"]:
        element = root.find(tag)
        for child in list(element):
            element.remove(child)

    # check if fractions contain nulls
    if df["Fractions"].isnull().any() or (df["Fractions"].astype(str).str.strip() == "").any():
        fractions_to_write = ["32767"] * len(df)
    else:
        fractions_to_write = df["Fractions"].astype(str).tolist()

    # build raw file path to write to mqpal.xml
    raw_path_prefix = cfg.get("rawFilePath", "").rstrip("/")

    # enable_lfq only effective when raw_subdir is set
    lfq_elem = root.find(".//lfqMode")
    enable_lfq = cfg.get("enable_lfq", False)
    if isinstance(enable_lfq, str):
        enable_lfq = enable_lfq.strip().lower() == "true"
    elif not isinstance(enable_lfq, bool):
        raise ValueError("enable_lfq must be a boolean or a string 'true'/'false'.")

    lfq_enable_flag = enable_lfq and (raw_subdir is not None)
    if lfq_elem is not None:
        lfq_elem.text = "1" if lfq_enable_flag else "0"

    for i, row in df.iterrows():
        
        # In circular RNA reference, .raw converted to .mzXML
        raw_name = row["RawFileName"]

        if raw_subdir:
            raw_name = os.path.splitext(raw_name)[0] + "_filtered.mzXML"

        full_raw_path = os.path.join(raw_path_prefix, raw_name)
        ref_channel = "" if "ReferenceChannel" not in row or pd.isna(row["ReferenceChannel"]) else str(row["ReferenceChannel"])

        ET.SubElement(root.find("filePaths"), "string").text = full_raw_path
        ET.SubElement(root.find("experiments"), "string").text = str(row["Experiments"])
        ET.SubElement(root.find("fractions"), "short").text = fractions_to_write[i]
        ET.SubElement(root.find("ptms"), "boolean").text = "False"
        ET.SubElement(root.find("paramGroupIndices"), "int").text = "0"
        ET.SubElement(root.find("referenceChannel"), "string").text = ref_channel

    # fix > escaping
    xml_str = ET.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=True).decode("utf-8")
    xml_str = xml_str.replace("&gt;", ">")

    if raw_subdir:
        xml_path = os.path.join(output_path, "mqpar_circ.xml")
    else:
        xml_path = os.path.join(output_path, "mqpar_linear.xml")
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
