import os
import re
import bibtexparser
from bibtexparser.bparser import BibTexParser

# --- Configuration ---
BIB_FILE = 'results/merged_output.bib'    # The bib file containing the new IDs and old_keys
INPUT_TEX = 'manuscript.tex'              # Your original LaTeX file
OUTPUT_TEX = 'results/manuscript_updated.tex' # Where to save the updated LaTeX file

def build_key_mapping(bib_filepath):
    """
    Reads the bib file and creates a dictionary mapping old keys to new keys.
    """
    key_map = {}
    
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    
    with open(bib_filepath, 'r', encoding='utf-8') as f:
        bib_database = bibtexparser.load(f, parser=parser)
        
    for entry in bib_database.entries:
        new_key = entry['ID']
        
        if 'old_keys' in entry:
            # Split the old_keys string by comma and strip extra spaces
            old_keys = [k.strip() for k in entry['old_keys'].split(',')]
            
            for old_key in old_keys:
                # Only add to map if it's actually different to avoid redundant operations
                if old_key and old_key != new_key:
                    key_map[old_key] = new_key
                    
    return key_map

def update_latex_file(tex_filepath, out_filepath, key_map):
    """
    Reads the tex file, finds citation commands, and replaces old keys.
    """
    with open(tex_filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # This regex looks for commands containing "cite" (like \cite, \citep, \citet, \nocite)
    # It accounts for optional arguments in brackets [...] and captures the keys inside the braces {...}
    cite_pattern = re.compile(r'(\\[a-zA-Z]*cite[a-zA-Z*]*\s*(?:\[[^\]]*\])*\s*\{)([^}]+)(\})')
    
    replacements_made = 0
    unique_keys_updated = set()
    
    def replacer(match):
        nonlocal replacements_made
        
        prefix = match.group(1)   
        keys_str = match.group(2) 
        suffix = match.group(3)   
        
        current_keys = [k.strip() for k in keys_str.split(',')]
        updated_keys = []
        
        for k in current_keys:
            if k in key_map:
                new_k = key_map[k]
                updated_keys.append(new_k)
                replacements_made += 1
                unique_keys_updated.add(k)
            else:
                updated_keys.append(k)
                
        return prefix + ', '.join(updated_keys) + suffix

    updated_content = cite_pattern.sub(replacer, content)
    
    # Safely create output directories if they do not exist
    out_dir = os.path.dirname(out_filepath)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    
    with open(out_filepath, 'w', encoding='utf-8') as f:
        f.write(updated_content)
        
    return replacements_made, unique_keys_updated

def main():
    if not os.path.exists(BIB_FILE):
        print(f"Error: Could not find the bibliography file at '{BIB_FILE}'.")
        return
        
    if not os.path.exists(INPUT_TEX):
        print(f"Error: Could not find the LaTeX file at '{INPUT_TEX}'.")
        return

    print(f"Reading mapping from '{BIB_FILE}'...")
    key_map = build_key_mapping(BIB_FILE)
    print(f"Loaded {len(key_map)} old key mappings.")
    
    if not key_map:
        print("No 'old_keys' fields found in the bib file. Nothing to update.")
        return
        
    print(f"\nProcessing LaTeX file '{INPUT_TEX}'...")
    replacements, updated_set = update_latex_file(INPUT_TEX, OUTPUT_TEX, key_map)
    
    print("\n" + "="*40)
    print("  UPDATE COMPLETE")
    print("="*40)
    print(f"Total citations updated : {replacements}")
    print(f"Unique keys replaced    : {len(updated_set)}")
    print(f"Saved to                : {OUTPUT_TEX}")
    print("="*40)

if __name__ == "__main__":
    main()