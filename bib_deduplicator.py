import os
import sys
import glob
import re
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
import unicodedata

# --- Configuration ---
INPUT_FOLDER = './bib_files'
OUTPUT_FILE = 'results/merged_output.bib'
OPTION_B_FILE = 'results/discarded_option_b.bib'
DUPLICATES_LOG_FILE = 'results/duplicates_log.txt'

FIELDS_TO_REMOVE = [
    'abstract', 'url', 'note', 'notes', 'source',
    'comment', 'comments', 'group', 'groups',
    'urldate', 'file'
]

# Common LaTeX escape sequences → plain text. Order matters.
_LATEX_ESCAPES = [
    (r"\\v\{([A-Za-z])\}", r"\1"),    
    (r"\\'\{([A-Za-z])\}", r"\1"),    
    (r'\\"\{([A-Za-z])\}', r"\1"),    
    (r"\\`\{([A-Za-z])\}", r"\1"),    
    (r"\\\^\{([A-Za-z])\}", r"\1"),   
    (r"\\~\{([A-Za-z])\}", r"\1"),    
    (r"\\c\{([A-Za-z])\}", r"\1"),    
    (r"\\k\{([A-Za-z])\}", r"\1"),    
    (r"\\r\{([A-Za-z])\}", r"\1"),    
    (r"\\=\{([A-Za-z])\}", r"\1"),    
    (r"\\u\{([A-Za-z])\}", r"\1"),    
    (r"\\H\{([A-Za-z])\}", r"\1"),    
    (r"\\d\{([A-Za-z])\}", r"\1"),    
    (r"\\b\{([A-Za-z])\}", r"\1"),    
    (r"\\v\s+([A-Za-z])", r"\1"),
    (r"\\'\s*([A-Za-z])", r"\1"),
    (r'\\"\s*([A-Za-z])', r"\1"),
    (r"\\`\s*([A-Za-z])", r"\1"),
    (r"\\\^\s*([A-Za-z])", r"\1"),
    (r"\\~\s*([A-Za-z])", r"\1"),
    (r"\\c\s+([A-Za-z])", r"\1"),
    (r"\\k\s+([A-Za-z])", r"\1"),
    (r"\\r\s+([A-Za-z])", r"\1"),
    (r"\\=\s*([A-Za-z])", r"\1"),
    (r"\\u\s+([A-Za-z])", r"\1"),
    (r"\\H\s+([A-Za-z])", r"\1"),
    (r"\\d\s+([A-Za-z])", r"\1"),
    (r"\\b\s+([A-Za-z])", r"\1"),
    (r"\\&", "and"),
    (r"\\%", "percent"),
    (r"\\\$", "USD"),
    (r"\\#", "num"),
    (r"\\_", "_"),
    (r"\\textbackslash", ""),
    (r"\\(?:textit|textbf|texttt|textrm|textsf|textsc|emph|mbox)\s*\{([^{}]*)\}", r"\1"),
    (r"\\(?:i|j)\b", "i"),
    (r"\\[A-Za-z]+\s*", ""),
]

_MATH_MODE_RE = re.compile(r"\$[^$]*\$")
_WHITESPACE_RE = re.compile(r"\s+")
# Allowed characters: alphanumeric, underscore, hyphen, and exclamation mark
_KEY_SAFE_RE = re.compile(r"[^A-Za-z0-9_\-!]")


def sanitize_latex(text):
    if not text:
        return ""
    s = str(text)
    s = _MATH_MODE_RE.sub("", s)
    s = s.replace("$$", "")
    for pattern, repl in _LATEX_ESCAPES:
        s = re.sub(pattern, repl, s)
    prev = None
    while prev != s:
        prev = s
        s = s.replace("{", "").replace("}", "")
    s = _WHITESPACE_RE.sub(" ", s).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def sanitize_key_part(text):
    return _KEY_SAFE_RE.sub("", sanitize_latex(text))


# ============================================================
# Monitor helper (Windows + Linux)
# ============================================================
def get_active_monitor_workarea():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            class RECT(ctypes.Structure):
                _fields_ = [("left",   ctypes.c_long),
                            ("top",    ctypes.c_long),
                            ("right",  ctypes.c_long),
                            ("bottom", ctypes.c_long)]
            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize",    ctypes.c_ulong),
                            ("rcMonitor", RECT),
                            ("rcWork",    RECT),
                            ("dwFlags",   ctypes.c_ulong)]

            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            MONITOR_DEFAULTTONEAREST = 2
            hmon = ctypes.windll.user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                r = mi.rcWork  
                return (r.left, r.top, r.right - r.left, r.bottom - r.top)
        except Exception:
            pass

    if sys.platform.startswith("linux"):
        try:
            import subprocess
            pos = subprocess.run(
                ["xdotool", "getmouselocation", "--shell"],
                capture_output=True, text=True, timeout=1
            )
            if pos.returncode == 0:
                cx = cy = None
                for line in pos.stdout.splitlines():
                    if line.startswith("X="): cx = int(line[2:])
                    if line.startswith("Y="): cy = int(line[2:])
                if cx is not None and cy is not None:
                    out = subprocess.run(
                        ["xrandr", "--query"], capture_output=True,
                        text=True, timeout=1
                    ).stdout
                    for m in re.finditer(r"(\d+)x(\d+)\+(\d+)\+(\d+)", out):
                        mw, mh, mx, my = map(int, m.groups())
                        if mx <= cx < mx + mw and my <= cy < my + mh:
                            return (mx, my, mw, mh)
        except Exception:
            pass
    return None


def _center_on_active_monitor(root, w, h):
    area = get_active_monitor_workarea()
    if area is not None:
        mx, my, mw, mh = area
        x = mx + (mw - w) // 2
        y = my + (mh - h) // 2
        x = max(mx, min(x, mx + mw - w))
        y = max(my, min(y, my + mh - h))
    else:
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
    return f"+{x}+{y}"


# ============================================================
# Text helpers
# ============================================================
def get_last_name(author_string):
    if not author_string:
        return "Unknown"
    cleaned = sanitize_latex(author_string)
    first_author = cleaned.split(' and ')[0].strip()
    if ',' in first_author:
        last_name = first_author.split(',')[0].strip()
    else:
        last_name = first_author.split()[-1].strip()
    last_name = sanitize_key_part(last_name)
    return last_name.capitalize() if last_name else "Unknown"


def get_words_from_title(title_string):
    cleaned = sanitize_latex(title_string)
    return cleaned.split()


def build_key(parts):
    last_name, year, first_words, last_words = parts
    key = f"{sanitize_key_part(last_name)}{sanitize_key_part(str(year))}" \
          f"{sanitize_key_part(first_words)}_{sanitize_key_part(last_words)}"
    return key if key.strip("_") else "Unknown"


def get_first_words(words):
    if not words:
        return "notitle"
    if len(words[0]) < 4 and len(words) > 1:
        return (words[0] + words[1]).lower()
    return words[0].lower()


def get_last_words(words):
    if not words:
        return "notitle"
    if len(words[-1]) < 4 and len(words) > 1:
        return (words[-2] + words[-1]).lower()
    return words[-1].lower()


def get_year_int(year_string):
    try:
        match = re.search(r'\d{4}', str(year_string))
        return int(match.group()) if match else 0
    except Exception:
        return 0


# ============================================================
# Duplicate confirmation dialog
# ============================================================
def prompt_user_for_duplicate(key1, title1, source1, key2, title2, source2):
    header_text   = "Possible duplicate found (3 of 4 parts match)"
    question_text = "Are these duplicates?"

    try:
        import tkinter as tk
        from tkinter import font as tkfont

        BG          = "#1e1e2e"
        CARD_KEEP   = "#1f3d2b"
        CARD_DROP   = "#3d1f24"
        ACCENT_KEEP = "#a6e3a1"
        ACCENT_DROP = "#f38ba8"
        TEXT_MAIN   = "#e6e6f0"
        TEXT_MUTED  = "#9aa0b5"
        BTN_YES     = "#a6e3a1"
        BTN_NO      = "#f38ba8"
        BTN_HOVER_Y = "#b8efb3"
        BTN_HOVER_N = "#ff9fb8"
        BTN_COPY    = "#6c7086"
        BTN_COPY_HV = "#8087a2"
        BTN_COPY_OK = "#a6e3a1"

        root = tk.Tk()
        root.title("Duplicate Check")
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        root.resizable(False, False)

        f_header   = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        f_section  = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        f_key      = tkfont.Font(family="Consolas", size=10)
        f_title    = tkfont.Font(family="Segoe UI", size=10)
        f_source   = tkfont.Font(family="Segoe UI", size=9, slant="italic")
        f_question = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        f_button   = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        f_small    = tkfont.Font(family="Segoe UI", size=9, weight="bold")

        def on_close():
            try: root.destroy()
            except Exception: pass
            os._exit(0)

        root.protocol("WM_DELETE_WINDOW", on_close)

        outer = tk.Frame(root, bg=BG, padx=22, pady=18)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text=header_text, font=f_header, bg=BG, fg=TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 14))

        def copy_to_clipboard(text, button):
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            original_text = button.cget("text")
            original_bg   = button.cget("bg")
            button.configure(text="Copied!", bg=BTN_COPY_OK, fg="#1e1e2e")
            def revert():
                try: button.configure(text=original_text, bg=original_bg, fg=TEXT_MAIN)
                except tk.TclError: pass
            root.after(900, revert)

        def build_card(parent, heading, card_bg, accent, key, title, source):
            card = tk.Frame(parent, bg=card_bg, padx=14, pady=12, highlightbackground=accent, highlightcolor=accent, highlightthickness=1)
            card.pack(fill="x", pady=(0, 10))
            head_row = tk.Frame(card, bg=card_bg)
            head_row.pack(fill="x")
            tk.Label(head_row, text=heading, font=f_section, bg=card_bg, fg=accent, anchor="w").pack(side="left")
            copy_btn = tk.Button(head_row, text="⧉ Copy key", font=f_small, bg=BTN_COPY, fg=TEXT_MAIN, activebackground=BTN_COPY_HV, activeforeground=TEXT_MAIN, relief="flat", bd=0, padx=10, pady=3, cursor="hand2", command=lambda: copy_to_clipboard(key, copy_btn))
            copy_btn.pack(side="right")
            copy_btn.bind("<Enter>", lambda e: copy_btn.configure(bg=BTN_COPY_HV))
            copy_btn.bind("<Leave>", lambda e: copy_btn.configure(bg=BTN_COPY))
            tk.Label(card, text=f"from: {source}", font=f_source, bg=card_bg, fg=TEXT_MUTED, anchor="w").pack(fill="x", pady=(4, 0))
            tk.Label(card, text="Key", font=f_section, bg=card_bg, fg=TEXT_MUTED, anchor="w").pack(fill="x", pady=(8, 0))
            tk.Label(card, text=key, font=f_key, bg=card_bg, fg=TEXT_MAIN, anchor="w", justify="left", wraplength=460).pack(fill="x")
            tk.Label(card, text="Title", font=f_section, bg=card_bg, fg=TEXT_MUTED, anchor="w").pack(fill="x", pady=(8, 0))
            tk.Label(card, text=title, font=f_title, bg=card_bg, fg=TEXT_MAIN, anchor="w", justify="left", wraplength=460).pack(fill="x")
            return card

        build_card(outer, "KEEPING  (higher priority)", CARD_KEEP, ACCENT_KEEP, key1, title1, source1)
        build_card(outer, "DISCARDING  (lower priority)", CARD_DROP, ACCENT_DROP, key2, title2, source2)

        tk.Label(outer, text=question_text, font=f_question, bg=BG, fg=TEXT_MAIN).pack(pady=(6, 12))

        btn_row = tk.Frame(outer, bg=BG)
        btn_row.pack(fill="x")

        result = {"value": None}

        def make_button(parent, text, bg, hover_bg, value):
            b = tk.Button(parent, text=text, font=f_button, bg=bg, fg="#1e1e2e", activebackground=hover_bg, activeforeground="#1e1e2e", relief="flat", bd=0, padx=18, pady=8, cursor="hand2", command=lambda: (result.__setitem__("value", value), root.destroy()))
            b.bind("<Enter>", lambda e: b.configure(bg=hover_bg))
            b.bind("<Leave>", lambda e: b.configure(bg=bg))
            return b

        yes_btn = make_button(btn_row, "Yes, merge", BTN_YES, BTN_HOVER_Y, True)
        no_btn  = make_button(btn_row, "No, keep both", BTN_NO, BTN_HOVER_N, False)
        yes_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        no_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        root.bind("<Return>", lambda e: (result.__setitem__("value", True),  root.destroy()))
        root.bind("<Escape>", lambda e: (result.__setitem__("value", False), root.destroy()))
        for k in ("y", "Y"): root.bind(k, lambda e: (result.__setitem__("value", True),  root.destroy()))
        for k in ("n", "N"): root.bind(k, lambda e: (result.__setitem__("value", False), root.destroy()))

        root.update_idletasks()
        w = root.winfo_width(); h = root.winfo_height()
        root.geometry(_center_on_active_monitor(root, w, h))

        root.mainloop()
        return bool(result["value"]) if result["value"] is not None else False

    except SystemExit:
        raise
    except Exception:
        print("\n" + "=" * 60)
        print("  POSSIBLE DUPLICATE (3 of 4 parts match)")
        print("=" * 60)
        print(f"  [KEEP]     {key1}")
        print(f"             {title1}")
        print(f"             from: {source1}")
        print("-" * 60)
        print(f"  [DISCARD]  {key2}")
        print(f"             {title2}")
        print(f"             from: {source2}")
        print("=" * 60)
        while True:
            ans = input("Merge as duplicate? (y/n): ").strip().lower()
            if ans in ("y", "yes"): return True
            if ans in ("n", "no"): return False
            print("Please answer 'y' or 'n'.")


# ============================================================
# Final summary dialog
# ============================================================
def show_summary_window(stats, output_file, option_b_file, log_file):
    try:
        import tkinter as tk
        from tkinter import font as tkfont

        BG           = "#1e1e2e"
        CARD_BG      = "#262637"
        ACCENT       = "#89b4fa"
        TEXT_MAIN    = "#e6e6f0"
        TEXT_MUTED   = "#9aa0b5"
        BTN_PRIMARY  = "#89b4fa"
        BTN_HOVER    = "#a5c8ff"
        BTN_OK       = "#a6e3a1"
        BTN_DISABLED = "#45475a"

        root = tk.Tk()
        root.title("Merge Summary")
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        root.resizable(False, False)

        f_header  = tkfont.Font(family="Segoe UI", size=13, weight="bold")
        f_section = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        f_value   = tkfont.Font(family="Segoe UI", size=10)
        f_mono    = tkfont.Font(family="Consolas", size=10)
        f_button  = tkfont.Font(family="Segoe UI", size=11, weight="bold")

        def on_close():
            try: root.destroy()
            except Exception: pass
            os._exit(0)

        root.protocol("WM_DELETE_WINDOW", on_close)

        outer = tk.Frame(root, bg=BG, padx=24, pady=20)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="Merge Complete", font=f_header, bg=BG, fg=TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 14))

        card = tk.Frame(outer, bg=CARD_BG, padx=16, pady=14, highlightbackground=ACCENT, highlightcolor=ACCENT, highlightthickness=1)
        card.pack(fill="x", pady=(0, 12))

        def add_stat_row(label, value):
            row = tk.Frame(card, bg=CARD_BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, font=f_section, bg=CARD_BG, fg=TEXT_MUTED, anchor="w", width=26).pack(side="left")
            tk.Label(row, text=str(value), font=f_value, bg=CARD_BG, fg=TEXT_MAIN, anchor="w").pack(side="left")

        add_stat_row("Input files scanned:", stats.get('files_scanned', 0))
        add_stat_row("Total entries read:", stats.get('total_entries', 0))
        add_stat_row("Exact duplicates (4/4):", stats.get('exact_duplicates', 0))
        add_stat_row("Approved merges (3/4):", stats.get('approved_merges', 0))
        add_stat_row("Rejected merges (kept):", stats.get('rejected_merges', 0))
        add_stat_row("Unique entries written:", stats.get('final_count', 0))
        add_stat_row("Entries discarded (opt B):", stats.get('discarded_count', 0))
        add_stat_row("Duplicate groups logged:", stats.get('duplicate_groups', 0))

        files_card = tk.Frame(outer, bg=CARD_BG, padx=16, pady=14, highlightbackground=ACCENT, highlightcolor=ACCENT, highlightthickness=1)
        files_card.pack(fill="x", pady=(0, 12))
        tk.Label(files_card, text="Output files", font=f_section, bg=CARD_BG, fg=TEXT_MUTED, anchor="w").pack(fill="x", pady=(0, 6))

        for label, path in [("Merged:", output_file), ("Option B:", option_b_file), ("Log:", log_file)]:
            row = tk.Frame(files_card, bg=CARD_BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, font=f_section, bg=CARD_BG, fg=TEXT_MUTED, anchor="w", width=10).pack(side="left")
            tk.Label(row, text=os.path.abspath(path), font=f_mono, bg=CARD_BG, fg=TEXT_MAIN, anchor="w", justify="left", wraplength=380).pack(side="left", fill="x")

        btn_row = tk.Frame(outer, bg=BG)
        btn_row.pack(fill="x", pady=(4, 0))

        def make_button(parent, text, bg, hover_bg, fg, command):
            b = tk.Button(parent, text=text, font=f_button, bg=bg, fg=fg, activebackground=hover_bg, activeforeground=fg, relief="flat", bd=0, padx=18, pady=8, cursor="hand2", command=command)
            b.bind("<Enter>", lambda e: b.configure(bg=hover_bg))
            b.bind("<Leave>", lambda e: b.configure(bg=bg))
            return b

        def copy_bib_contents():
            try:
                with open(output_file, 'r', encoding='utf-8') as f: content = f.read()
            except Exception as e:
                copy_btn.configure(text=f"Error: {e}", bg=BTN_DISABLED, state="disabled", fg=TEXT_MAIN)
                return
            root.clipboard_clear()
            root.clipboard_append(content)
            root.update()
            original_text = copy_btn.cget("text")
            original_bg   = copy_btn.cget("bg")
            copy_btn.configure(text="✓ Copied to clipboard!", bg=BTN_OK, fg="#1e1e2e")
            def revert():
                try: copy_btn.configure(text=original_text, bg=original_bg, fg="#1e1e2e")
                except tk.TclError: pass
            root.after(1400, revert)

        copy_btn = make_button(btn_row, "⧉ Copy merged_output.bib", BTN_PRIMARY, BTN_HOVER, "#1e1e2e", copy_bib_contents)
        close_btn = make_button(btn_row, "Close", "#45475a", "#585b70", TEXT_MAIN, lambda: (root.destroy(), os._exit(0)))

        copy_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        close_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        root.bind("<Escape>", lambda e: (root.destroy(), os._exit(0)))

        root.update_idletasks()
        w = root.winfo_width(); h = root.winfo_height()
        root.geometry(_center_on_active_monitor(root, w, h))
        root.mainloop()

    except SystemExit:
        raise
    except Exception:
        pass


# ============================================================
# Main pipeline
# ============================================================
def process_bib_files(input_folder, output_file, option_b_file, log_file_path):
    all_entries = []

    # 1. READ ALL FILES AND PREPARE ENTRIES
    bib_files = glob.glob(os.path.join(input_folder, '*.bib'))
    if not bib_files:
        print(f"No .bib files found in '{input_folder}'.")
        return
    output_dir = os.path.dirname(output_file) or "."
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False

    entry_counter = 1
    for filepath in bib_files:
        filename = os.path.basename(filepath)
        with open(filepath, 'r', encoding='utf-8') as bibtex_file:
            bib_database = bibtexparser.load(bibtex_file, parser=parser)

            for entry in bib_database.entries:
                original_id = entry.get('ID', 'unknown_id')
                original_title = entry.get('title', 'notitle').replace('\n', ' ').strip()

                for field in FIELDS_TO_REMOVE:
                    entry.pop(field, None)

                author = entry.get('author', '')
                year = entry.get('year', '0000')
                title = entry.get('title', '')

                parts = (
                    get_last_name(author),
                    year,
                    get_first_words(get_words_from_title(title)),
                    get_last_words(get_words_from_title(title))
                )

                temp_key  = f"{entry_counter}{parts[0]}{parts[1]}{parts[2]}!{parts[3]}"
                clean_key = build_key(parts)

                all_entries.append({
                    'prefix': entry_counter,
                    'temp_key': temp_key,
                    'clean_key': clean_key,
                    'original_id': original_id,
                    'original_title': original_title,
                    'source_file': filename,
                    'parts': parts,
                    'year_int': get_year_int(parts[1]),
                    'bib_dict': entry
                })
                entry_counter += 1

    # 2. GROUP EXACT MATCHES (4/4)
    exact_groups = {}
    for item in all_entries:
        exact_groups.setdefault(item['parts'], []).append(item)

    grouped_list = []
    for parts, items in exact_groups.items():
        max_year = max(i['year_int'] for i in items)
        grouped_list.append({'parts': parts, 'items': items, 'max_year': max_year})

    grouped_list.sort(key=lambda g: g['max_year'], reverse=True)

    # 3. RESOLVE 3/4 MATCHES
    final_merged_groups = []
    approved_merges = 0        
    rejected_merges = 0        

    for current_group in grouped_list:
        merged = False
        for existing_group in final_merged_groups:
            matches = sum(1 for a, b in zip(current_group['parts'],
                                            existing_group['parts']) if a == b)

            if matches == 3:
                best_existing = max(existing_group['items'],
                                    key=lambda x: x['year_int'])
                best_current  = max(current_group['items'],
                                    key=lambda x: x['year_int'])

                if prompt_user_for_duplicate(
                best_existing['clean_key'],
                best_existing['original_title'],
                best_existing['source_file'],
                best_current['clean_key'],
                best_current['original_title'],
                best_current['source_file'],
            ):
                    existing_group['items'].extend(current_group['items'])
                    merged = True
                    approved_merges += 1
                    break
                else:
                    rejected_merges += 1

        if not merged:
            final_merged_groups.append(current_group)

    # 4. FINALIZE WINNERS AND LOGS
    final_entries = []
    discarded_entries = []
    duplicates_found = 0

    with open(log_file_path, 'w', encoding='utf-8') as log_file:
        for group in final_merged_groups:
            items = sorted(group['items'], key=lambda x: x['year_int'], reverse=True)

            winner = items[0]
            losers = items[1:]

            final_key = build_key(winner['parts'])

            winner_entry = winner['bib_dict']
            winner_entry['ID'] = final_key

            all_old_ids = [item['original_id'] for item in items]
            winner_entry['old_keys'] = ', '.join(all_old_ids)

            final_entries.append(winner_entry)

            if losers:
                duplicates_found += 1
                log_file.write(f"{final_key} : {winner['original_title']}\n")
                log_file.write("------------------\n")

                for item in items:
                    log_file.write(
                        f"{item['original_id']} : "
                        f"{item['original_title']} : {item['source_file']}\n"
                    )
                log_file.write("\n")

                for loser in losers:
                    loser_entry = loser['bib_dict']
                    loser_key = build_key(loser['parts'])
                    
                    # Removed suffix logic completely to match output requirements.
                    loser_entry['ID'] = loser_key
                    discarded_entries.append(loser_entry)

    # 5. WRITE OUT
    writer = BibTexWriter()
    writer.indent = '  '

    out_db = bibtexparser.bibdatabase.BibDatabase()
    out_db.entries = final_entries
    with open(output_file, 'w', encoding='utf-8') as out_file:
        out_file.write(writer.write(out_db))

    opt_b_db = bibtexparser.bibdatabase.BibDatabase()
    opt_b_db.entries = discarded_entries
    with open(option_b_file, 'w', encoding='utf-8') as opt_b_out:
        opt_b_out.write(writer.write(opt_b_db))

    # ---------- Stats ----------
    stats = {
        'files_scanned':    len(bib_files),
        'total_entries':    len(all_entries),
        'exact_duplicates': sum(len(items) - 1 for items in exact_groups.values()),
        'approved_merges':  approved_merges,
        'rejected_merges':  rejected_merges,
        'final_count':      len(final_entries),
        'discarded_count':  len(discarded_entries),
        'duplicate_groups': duplicates_found,
    }

    print(f"Success! Merged {len(final_entries)} unique entries into '{output_file}'")
    print(f"Saved {len(discarded_entries)} discarded duplicates to '{option_b_file}'")
    print(f"Found and logged {duplicates_found} duplicate groups in '{log_file_path}'")

    show_summary_window(stats, output_file, option_b_file, log_file_path)


def main():
    process_bib_files(INPUT_FOLDER, OUTPUT_FILE, OPTION_B_FILE, DUPLICATES_LOG_FILE)

if __name__ == "__main__":
    main()