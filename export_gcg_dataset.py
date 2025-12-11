import argparse
import json
import os
import sys
from pathlib import Path
from copy import deepcopy

# Add current directory to path so we can import from struq and config
sys.path.append(os.getcwd())

from struq import jload, jdump
from config import PROMPT_FORMAT, TEST_INJECTED_PROMPT, DELIMITERS

def parse_args():
    parser = argparse.ArgumentParser(description="Export GCG attack logs to a JSONL dataset.")
    parser.add_argument("--model_path", type=str, required=True, help="Path to the model directory containing GCG logs (e.g., in a 'gcg' subdirectory).")
    parser.add_argument("--data_path", type=str, default="data/davinci_003_outputs.json", help="Path to the original dataset file.")
    parser.add_argument("--out_path", type=str, required=True, help="Path to save the output JSONL dataset.")
    parser.add_argument("--only_success", action="store_true", help="Only export successful attacks.")
    return parser.parse_args()

def load_lora_model_info(model_path):
    """
    Extracts frontend delimiters and training attacks from the model path, similar to load_lora_model in test.py.
    """
    # This logic mimics load_lora_model in test.py to get delimiters
    # configs = model_name_or_path.split('/')[-1].split('_') + ['Frontend-Delimiter-Placeholder', 'None']
    # frontend_delimiters = configs[1] if configs[1] in DELIMITERS else base_model_path.split('/')[-1]
    
    # We assume model_path might be a full path, so we take the basename
    model_name = os.path.basename(os.path.normpath(model_path))
    configs = model_name.split('_') + ['Frontend-Delimiter-Placeholder', 'None']
    
    frontend_delimiters = configs[1] if len(configs) > 1 and configs[1] in DELIMITERS else model_name
    
    # If not found in DELIMITERS, it might be a base model or different naming convention. 
    # The user instruction says: "Extract frontend_delimiters by parsing model_path the same way load_lora_model() does."
    # In test.py: 
    # base_model_path = model_name_or_path
    # frontend_delimiters = configs[1] if configs[1] in DELIMITERS else base_model_path.split('/')[-1]
    
    if frontend_delimiters not in DELIMITERS:
        # Fallback or maybe it's the model name itself if it's a base model
        # But usually for StruQ models it follows the naming convention.
        # If it's a base model like 'llama-7b', it might be in DELIMITERS.
        if model_name in DELIMITERS:
            frontend_delimiters = model_name
            
    return frontend_delimiters

def main():
    args = parse_args()
    
    print(f"Loading original data from {args.data_path}...")
    orig_data = jload(args.data_path)
    
    # Filter data exactly as test.py does
    filtered_data = [d for d in orig_data if d["input"] != ""]
    print(f"Found {len(filtered_data)} examples after filtering empty inputs.")
    
    # Map index to example for easy lookup
    # The sample_id in logs corresponds to the index in this filtered list
    idx_to_example = {i: d for i, d in enumerate(filtered_data)}
    
    model_path = Path(args.model_path)
    gcg_root = model_path / "gcg"
    
    if not gcg_root.exists():
        # Fallback: check if logs are in model_path-log/gcg if model_path doesn't exist or doesn't have gcg
        # test.py logic: 
        # cfg.log_dir = args.model_name_or_path if os.path.exists(args.model_name_or_path) else (args.model_name_or_path+'-log')
        # But here we assume model_path is the one passed in.
        # If the user passed the model dir, gcg should be inside.
        print(f"Warning: {gcg_root} does not exist.")
        # Try checking if it's a log dir itself or if there is a -log suffix
        if str(model_path).endswith("-log"):
             gcg_root = model_path / "gcg"
        else:
             gcg_root = Path(str(model_path) + "-log") / "gcg"
        
        if not gcg_root.exists():
             print(f"Error: Could not find GCG logs at {gcg_root}")
             return

    print(f"Scanning GCG logs in {gcg_root}...")
    
    log_files = list(gcg_root.rglob("*.jsonl"))
    print(f"Found {len(log_files)} log files.")
    
    frontend_delimiters = load_lora_model_info(str(model_path))
    print(f"Detected frontend delimiters: {frontend_delimiters}")
    
    prompt_format = PROMPT_FORMAT.get(frontend_delimiters, None)
    if prompt_format is None:
        print(f"Warning: Could not find PROMPT_FORMAT for {frontend_delimiters}. Structured prompts might be skipped or incorrect.")
    
    exported_count = 0
    success_count = 0
    
    with open(args.out_path, "w", encoding="utf-8") as out_f:
        for log_file in log_files:
            try:
                # Read the last line of the log file
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if not lines:
                        continue
                    last_line = lines[-1]
                    log_entry = json.loads(last_line)
                
                # Extract info
                # The log entry structure depends on GCGAttack logger. 
                # Based on test.py it uses GCGAttack which uses attack._setup_log_file(cfg).
                # Usually GCG logs have 'sample_id', 'loss', 'best_suffix', 'generated', 'is_success' etc.
                # Let's assume standard fields from the user description:
                # sample_id, suffix (or adv_suffix), generated, success_in_response
                
                # Note: In test.py gcg() function:
                # cfg.sample_id = d_item["id"] -> This might be the original ID if 'id' key exists, 
                # BUT test_gcg passes sample_ids=list(range(len(data))) if None.
                # And data is filtered.
                # So sample_id in log likely corresponds to the index in filtered_data IF test.py was run with default sample_ids.
                # However, if sample_ids were passed explicitly to test.py, cfg.sample_id takes that value.
                # The user says: "Convert sample_id -> idx = int(sample_id) and pick example = filtered[idx]."
                # This implies sample_id in log IS the index.
                
                sample_id = int(log_file.stem) # Usually filename is sample_id.jsonl or similar, or inside json.
                # User said: <sample_id>.jsonl. So filename is the ID.
                # Let's verify if inside json it's also present.
                if "sample_id" in log_entry:
                    sample_id = int(log_entry["sample_id"])
                
                if sample_id not in idx_to_example:
                    print(f"Warning: Sample ID {sample_id} not found in filtered data. Skipping.")
                    continue
                
                example = idx_to_example[sample_id]
                
                # Extract fields
                # The user mentioned 'suffix' or 'adv_suffix'. 
                # In typical GCG logs it's often 'adv_suffix' or 'best_suffix'.
                # Let's look for likely keys.
                gcg_suffix = log_entry.get("adv_suffix") or log_entry.get("best_suffix") or log_entry.get("suffix")
                
                # generated response
                generated = log_entry.get("generated") or log_entry.get("gen_str")
                
                # success
                # User says: "success_in_response (bool; they already compute whether injected word appears)"
                success = log_entry.get("success_in_response", False)
                
                if args.only_success and not success:
                    continue
                
                # Reconstruct inputs
                clean_instruction = example.get("instruction", "")
                clean_input = example.get("input", "")
                clean_output = example.get("output", "")
                
                injected_prompt = TEST_INJECTED_PROMPT
                
                # adv_input = clean_input + " " + injected_prompt.capitalize() + " " + gcg_suffix
                # Note: In test.py gcg():
                # d_item["input"] += ' ' + TEST_INJECTED_PROMPT.capitalize() + ' ' + adv_suffix
                adv_input = f"{clean_input} {injected_prompt.capitalize()} {gcg_suffix}"
                
                record = {
                    "id": sample_id,
                    "original_instruction": clean_instruction,
                    "original_input": clean_input,
                    "original_output": clean_output,
                    "attack_type": "gcg",
                    "injected_prompt": injected_prompt,
                    "gcg_suffix": gcg_suffix,
                    "adv_input": adv_input,
                    "adv_model_output": generated,
                    "success_in_response": success,
                    "model_name": os.path.basename(str(model_path)),
                    "frontend_delimiters": frontend_delimiters
                }
                
                # Optional: Structured prompts
                if prompt_format:
                    try:
                        structured_clean_prompt = prompt_format["prompt_input"].format_map(
                            {"instruction": clean_instruction, "input": clean_input}
                        )
                        structured_adv_prompt = prompt_format["prompt_input"].format_map(
                            {"instruction": clean_instruction, "input": adv_input}
                        )
                        record["structured_clean_prompt"] = structured_clean_prompt
                        record["structured_adv_prompt"] = structured_adv_prompt
                    except Exception as e:
                        # Fallback if formatting fails
                        pass

                # Write to output
                out_f.write(json.dumps(record) + "\n")
                exported_count += 1
                if success:
                    success_count += 1
                    
            except Exception as e:
                print(f"Error processing {log_file}: {e}")
                continue

    print(f"Export completed. Processed {exported_count} records ({success_count} successful).")
    print(f"Saved to {args.out_path}")

if __name__ == "__main__":
    main()
