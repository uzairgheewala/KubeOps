#!/usr/bin/env python3
import os
import sys
import math
import time
import argparse
import sqlite3
import concurrent.futures
from collections import defaultdict, Counter
from typing import Dict, Tuple, Any, List, Optional

# --------------------
# Defaults & constants
# --------------------

DEFAULT_EXTENSIONS = {
    ".py": "Python",
    ".html": "HTML",
    ".css": "CSS",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript JSX",
    ".md": "Markdown",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
}

DEFAULT_EXCLUDE_DIRS = {
    "__pycache__", "public", "repositories",
    "demos", "migrations",
    "node_modules", "archived_static",
    "admin", "rest_framework", "vendor",
    ".git", ".hg", ".svn", 
    "n8n-exports",
}

DEFAULT_EXCLUDE_FILES = {
    "package-lock.json",
}

DEFAULT_ALLOWED_STATIC_SUBDIRS = {"css", "js", "html"}

CACHE_FILENAME = ".countlines.cache.db"

# --------------------
# Utility & DB Cache
# --------------------

def human_int(n: int) -> str:
    return f"{n:,}"

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_cache (
            filepath TEXT PRIMARY KEY,
            size INTEGER,
            mtime REAL,
            non_empty INTEGER,
            total INTEGER
        )
    """)
    conn.commit()
    return conn

def load_cache_dict(conn: sqlite3.Connection) -> Dict[str, Tuple[int, float, int, int]]:
    """Loads the DB into memory: {filepath: (size, mtime, non_empty, total)}"""
    cursor = conn.cursor()
    cursor.execute("SELECT filepath, size, mtime, non_empty, total FROM file_cache")
    return {row[0]: (row[1], row[2], row[3], row[4]) for row in cursor.fetchall()}

def is_text_file_safe(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as f:
            f.read(4096)
        return True
    except UnicodeDecodeError:
        return False
    except Exception:
        return True 

def count_lines_in_file(file_path: str) -> Tuple[int, int]:
    non_empty = 0
    total = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            total += 1
            if line.strip():
                non_empty += 1
    return non_empty, total

# --------------------
# Core walker + filter
# --------------------

class ExcludeStats:
    def __init__(self):
        self.by_reason = Counter()
        self.by_extension = Counter()
        self.by_dirname = Counter()
        self.unreadable = 0
        self.files: List[Tuple[str, str, str, os.stat_result]] = []      
        self.dir_paths: List[Tuple[str, str, str]] = []  

    def inc(self, reason: str, path: str = "", ext: str = "", dirname: str = "", stat: Optional[os.stat_result] = None):
        self.by_reason[reason] += 1
        if ext:
            self.by_extension[ext] += 1
        if dirname:
            self.by_dirname[dirname] += 1
        if path and stat:
            self.files.append((path, ext, reason, stat))

    def add_dir(self, dir_path: str, reason: str, dirname: str):
        self.by_reason[reason] += 1
        if dirname:
            self.by_dirname[dirname] += 1
        self.dir_paths.append((dir_path, reason, dirname))

    def bump_unreadable(self):
        self.unreadable += 1

    def summarize_small(self) -> str:
        lines = []
        if self.by_reason:
            top_reasons = ", ".join(f"{k}: {v}" for k, v in self.by_reason.most_common())
            lines.append(f"Excluded (by reason): {top_reasons}")
        if self.by_extension:
            top_exts = ", ".join(f"{k}: {v}" for k, v in self.by_extension.most_common(10))
            lines.append(f"Excluded by extension (top 10): {top_exts}")
        if self.by_dirname:
            top_dirs = ", ".join(f"{k}: {v}" for k, v in self.by_dirname.most_common(10))
            lines.append(f"Excluded by directory (top 10): {top_dirs}")
        if self.unreadable:
            lines.append(f"Unreadable/Binary or I/O errors: {self.unreadable}")
        return "\n".join(lines) if lines else "(No exclusions recorded)"

def fast_walk(
    root_dir: str,
    extensions: Dict[str, str],
    exclude_dirs: set,
    exclude_files: set,
    allowed_static_subdirs: set,
    include_dotfiles: bool,
    excl_stats: ExcludeStats,
):
    """Recursive os.scandir generator yielding (filepath, ext, lang, stat_result)"""
    root_dir = os.path.abspath(root_dir)

    def _walk(current_dir, parts_depth):
        try:
            with os.scandir(current_dir) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        d = entry.name
                        if d in exclude_dirs:
                            excl_stats.add_dir(entry.path, "excluded_dir", d)
                            continue
                        
                        # static/website filter
                        if parts_depth > 0 and current_dir.endswith(f"{os.sep}static") and f"{os.sep}website{os.sep}static" in current_dir:
                            if d not in allowed_static_subdirs:
                                excl_stats.add_dir(entry.path, "static_filtered", d)
                                continue

                        yield from _walk(entry.path, parts_depth + 1)

                    elif entry.is_file(follow_symlinks=False):
                        if not include_dotfiles and entry.name.startswith("."):
                            excl_stats.inc("dotfile")
                            continue

                        stat = entry.stat()
                        base = entry.name

                        if base in exclude_files:
                            _, ext = os.path.splitext(base)
                            excl_stats.inc("excluded_file", path=entry.path, ext=ext.lower(), dirname=base, stat=stat)
                            continue

                        _, ext = os.path.splitext(base)
                        ext = ext.lower()

                        if ext not in extensions:
                            excl_stats.inc("untracked_extension", path=entry.path, ext=ext, stat=stat)
                            continue

                        yield entry.path, ext, extensions[ext], stat
        except PermissionError:
            pass

    yield from _walk(root_dir, 0)

# --------------------
# Progress bar helper
# --------------------

def _render_progress(prefix: str, done: int, total: int, start_ts: float, width: int = 20):
    elapsed = max(time.time() - start_ts, 1e-6)
    done = min(done, total)
    frac = (done / total) if total > 0 else 1.0
    filled = int(width * frac)
    bar = "█" * filled + "░" * (width - filled)
    rate = done / elapsed
    remaining = (total - done) / rate if rate > 0 else 0.0
    
    out = f"\r{prefix} [{bar}] {done}/{total} {frac*100:3.0f}% ETA: {int(remaining)}s"
    sys.stdout.write(out.ljust(79))
    sys.stdout.flush()
    if done >= total:
        sys.stdout.write("\n")
        sys.stdout.flush()

# --------------------
# Thread Worker 
# --------------------

def process_single_file(path: str, ext: str, stat: os.stat_result, cache_dict: dict, use_cache: bool) -> tuple:
    """Thread-safe function to count lines or fetch from dictionary cache."""
    f_size, f_mtime = stat.st_size, stat.st_mtime

    if use_cache and path in cache_dict:
        c_size, c_mtime, non_empty, total = cache_dict[path]
        if c_size == f_size and c_mtime == f_mtime:
            return path, ext, f_size, f_mtime, non_empty, total, True

    if not is_text_file_safe(path):
        return path, ext, f_size, f_mtime, 0, 0, False

    try:
        non_empty, total = count_lines_in_file(path)
        return path, ext, f_size, f_mtime, non_empty, total, False
    except (UnicodeDecodeError, OSError):
        return path, ext, f_size, f_mtime, 0, 0, False

# --------------------
# Main counting
# --------------------

def process(
    root_dir: str,
    mode: str,
    extensions: Dict[str, str],
    exclude_dirs: set,
    exclude_files: set,
    allowed_static_subdirs: set,
    cache_path: str,
    use_cache: bool,
    clear_cache: bool,
    show_top: bool,
    show_excluded_stats: bool,
):
    conn = None
    cache_dict = {}
    if use_cache:
        if clear_cache and os.path.exists(cache_path):
            os.remove(cache_path)
        conn = init_db(cache_path)
        cache_dict = load_cache_dict(conn)

    excl_stats = ExcludeStats()
    line_counts = defaultdict(int)
    file_counts = defaultdict(int)
    files_details = defaultdict(list)
    updates_for_db = []

    print("Scanning directory for files to process...")
    files_to_process = list(fast_walk(
        root_dir, extensions, exclude_dirs, exclude_files,
        allowed_static_subdirs, False, excl_stats
    ))

    total_files = len(files_to_process)
    start_ts = time.time()
    last_tick = 0.0
    processed_count = 0

    # Execute Multithreading
    max_threads = min(32, (os.cpu_count() or 1) * 4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {
            executor.submit(process_single_file, path, ext, stat, cache_dict, use_cache): path 
            for path, ext, lang, stat in files_to_process
        }

        for future in concurrent.futures.as_completed(futures):
            processed_count += 1
            now = time.time()
            if (now - last_tick) >= 0.05 or processed_count == total_files:
                _render_progress("Counting files", processed_count, total_files, start_ts, width=20)
                last_tick = now

            try:
                path, ext, f_size, f_mtime, non_empty, total, used_cache = future.result()
            except Exception:
                excl_stats.bump_unreadable()
                continue

            if non_empty == 0 and total == 0:
                continue

            if not used_cache:
                updates_for_db.append((path, f_size, f_mtime, non_empty, total))
                # Update memory dict immediately so excluded files pass doesn't duplicate work
                cache_dict[path] = (f_size, f_mtime, non_empty, total)

            mode_lines = non_empty if mode == "nonempty" else total
            line_counts[ext] += mode_lines
            file_counts[ext] += 1
            files_details[ext].append((path, mode_lines))

    if use_cache and updates_for_db:
        conn.executemany(
            "INSERT OR REPLACE INTO file_cache (filepath, size, mtime, non_empty, total) VALUES (?, ?, ?, ?, ?)", 
            updates_for_db
        )
        conn.commit()

    if show_top:
        print("\nRanking of top files per file type")
        print("-----------------------------------")
        for ext, language in extensions.items():
            details = files_details.get(ext, [])
            if not details: continue
            max_lines = max(cnt for _, cnt in details)
            if max_lines == 0: continue
            power = 10 ** int(math.floor(math.log10(max_lines)))
            top_files = sorted([(p, c) for p, c in details if c >= power], key=lambda x: x[1], reverse=True)
            print(f"{language} ({ext}): threshold ≥ {power} lines (largest power={power})")
            for idx, (p, c) in enumerate(top_files[:25], start=1):
                print(f"  {idx:>2}. {p} — {human_int(c)}")
            print(f"  Sum of top files: {human_int(sum(c for _, c in top_files))}\n")

    total_lines = sum(line_counts.values())
    print("\nLine Count Summary")
    print("------------------")
    for ext, language in extensions.items():
        if line_counts[ext] > 0:
            print(f"{language:12s} ({ext:6s}): {human_int(line_counts[ext])}  across {human_int(file_counts[ext])} files")
    print("------------------")
    print(f"Total: {human_int(total_lines)} lines ({'non-empty' if mode=='nonempty' else 'all'} mode)")

    if show_excluded_stats:
        print("\nExcluded summary (small roll-up)")
        print("--------------------------------")
        print(excl_stats.summarize_small())

    return total_lines, dict(line_counts), excl_stats, conn, cache_dict


def summarize_excluded_lines(
    excl_stats: ExcludeStats,
    mode: str,
    extensions: Dict[str, str],
    conn: sqlite3.Connection,
    cache_dict: dict,
    use_cache: bool,
    which: str,
    limit: int,
    show_progress: bool,
):
    if which == "off":
        if conn: conn.close()
        return

    def want_ext(ext: str) -> bool:
        return which == "all" or ext in extensions

    candidates = []

    # Excluded files
    for path, ext, reason, stat in excl_stats.files:
        ext = (ext or "").lower()
        if want_ext(ext):
            candidates.append((path, ext, stat))
            if len(candidates) >= limit: break

    # Excluded dirs (using scandir for speed)
    # Excluded dirs (using scandir for speed)
    if len(candidates) < limit:
        gather_start_ts = time.time()
        gather_last_tick = 0.0

        def _scan_excluded(d_path):
            nonlocal gather_last_tick
            try:
                with os.scandir(d_path) as it:
                    for entry in it:
                        if len(candidates) >= limit: 
                            return
                        
                        # Live, throttled UI counter
                        now = time.time()
                        if (now - gather_last_tick) >= 0.1:
                            sys.stdout.write(f"\rGathering excluded files... {len(candidates):,} found".ljust(79))
                            sys.stdout.flush()
                            gather_last_tick = now

                        if entry.is_dir(follow_symlinks=False):
                            _scan_excluded(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            _, fext = os.path.splitext(entry.name)
                            fext = fext.lower()
                            if want_ext(fext):
                                candidates.append((entry.path, fext, entry.stat()))
            except (OSError, PermissionError):
                pass
                
        for dir_path, reason, dirname in excl_stats.dir_paths:
            _scan_excluded(dir_path)
            if len(candidates) >= limit: 
                break
        
        # Lock in the final count on a new line
        sys.stdout.write(f"\rGathering excluded files... {len(candidates):,} found. Done!\n".ljust(79))
        sys.stdout.flush()

    print("\nExcluded Line Count Summary")
    print("---------------------------")
    if not candidates:
        print("(No excluded files measured)")
        if conn: conn.close()
        return

    per_ext_lines = defaultdict(int)
    per_ext_files = defaultdict(int)
    hits, misses, skipped = 0, 0, 0
    updates_for_db = []
    
    total_candidates = len(candidates)
    start_ts = time.time()
    last_tick = 0.0
    processed_count = 0
    
    max_threads = min(32, (os.cpu_count() or 1) * 4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {
            executor.submit(process_single_file, path, ext, stat, cache_dict, use_cache): path 
            for path, ext, stat in candidates
        }

        for future in concurrent.futures.as_completed(futures):
            processed_count += 1
            if show_progress:
                now = time.time()
                if (now - last_tick) >= 0.05 or processed_count == total_candidates:
                    _render_progress("Measuring excluded files", processed_count, total_candidates, start_ts)
                    last_tick = now

            try:
                path, ext, f_size, f_mtime, non_empty, total, used_cache = future.result()
            except Exception:
                skipped += 1
                continue

            if non_empty == 0 and total == 0:
                skipped += 1
            else:
                if used_cache: hits += 1
                else: 
                    misses += 1
                    updates_for_db.append((path, f_size, f_mtime, non_empty, total))

                lines = non_empty if mode == "nonempty" else total
                key = ext or "(no-ext)"
                per_ext_lines[key] += lines
                per_ext_files[key] += 1

    if use_cache and updates_for_db:
        conn.executemany(
            "INSERT OR REPLACE INTO file_cache (filepath, size, mtime, non_empty, total) VALUES (?, ?, ?, ?, ?)", 
            updates_for_db
        )
        conn.commit()

    # Cache Cleanup Phase (Bulk SQLite Operation)
    if use_cache:
        print("\nCleaning up stale cache entries...")
        active_paths = {p for p, _, _, _ in files_to_process_global} # Need global ref
        active_paths.update(p for p, _, _ in candidates)
        
        # SQLite handles bulk deletes natively and near-instantly
        all_cached_paths = set(cache_dict.keys())
        stale_paths = [(p,) for p in all_cached_paths if p not in active_paths]
        if stale_paths:
            conn.executemany("DELETE FROM file_cache WHERE filepath = ?", stale_paths)
            conn.commit()
            
        conn.close()

    total_sum = 0
    for ext, lang in extensions.items():
        if per_ext_files.get(ext, 0) > 0:
            print(f"{lang:12s} ({ext:6s}): {human_int(per_ext_lines[ext])}  across {human_int(per_ext_files[ext])} files")
            total_sum += per_ext_lines[ext]

    for ext, cnt in per_ext_files.items():
        if ext not in extensions and cnt > 0:
            label = ext if ext != "(no-ext)" else "Other"
            print(f"{label:12s} ({ext:6s}): {human_int(per_ext_lines[ext])}  across {human_int(cnt)} files")
            total_sum += per_ext_lines[ext]

    print(f"(Excluded cache stats: {hits} hits, {misses} computed, {skipped} empty/unreadable, {total_candidates} candidates)")
    print("---------------------------")
    print(f"Total excluded: {human_int(total_sum)} lines ({'non-empty' if mode=='nonempty' else 'all'} mode)")


# --------------------
# CLI
# --------------------
# Global hack for stale path cleanup logic
files_to_process_global = [] 

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Count lines by extension with caching and exclusion stats.")
    p.add_argument("--root", default=os.getcwd(), help="Root directory to scan (default: cwd)")
    p.add_argument("--mode", choices=["nonempty", "all"], default="nonempty", help="Counting mode")
    p.add_argument("--ext", action="append", help="Track extra extension mapping")
    p.add_argument("--only-ext", action="append", help="Restrict to exactly these extensions")
    p.add_argument("--exclude-dir", action="append", help="Add an extra directory name to exclude")
    p.add_argument("--exclude-file", action="append", help="Exclude files by exact filename")
    p.add_argument("--excluded-lines", choices=["off", "tracked", "all"], default="tracked")
    p.add_argument("--allow-static", action="append", help="Allowed immediate subdirs under website/static")
    p.add_argument("--no-cache", action="store_true", help="Disable cache for this run")
    p.add_argument("--clear-cache", action="store_true", help="Clear all cache entries before scanning")
    p.add_argument("--cache-file", default=CACHE_FILENAME, help="Cache file path")
    p.add_argument("--no-top", action="store_true", help="Hide 'top files per type' section")
    p.add_argument("--no-excluded-stats", action="store_true", help="Hide excluded roll-up section")
    p.add_argument("--include-dotfiles", action="store_true", help="Include files that start with a dot")
    p.add_argument("--no-progress", action="store_true", help="Disable progress bar for excluded-line measurement")
    p.add_argument("--excluded-limit", type=int, default=500_000, help="Soft cap on excluded files measured")
    return p.parse_args(argv)

def build_extension_map(args) -> Dict[str, str]:
    if args.only_ext:
        ext_map = {}
        for e in args.only_ext:
            k, v = (e.split("=", 1) if "=" in e else (e, e.lstrip(".")))
            ext_map[k.strip().lower()] = v.strip()
        return ext_map
    ext_map = dict(DEFAULT_EXTENSIONS)
    if args.ext:
        for ent in args.ext:
            k, v = ent.split("=", 1)
            ext_map[k.strip().lower()] = v.strip()
    return ext_map

def main(argv=None):
    global files_to_process_global
    args = parse_args(argv)
    extensions = build_extension_map(args)

    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS)
    if args.exclude_dir: exclude_dirs.update(args.exclude_dir)

    exclude_files = set(DEFAULT_EXCLUDE_FILES)
    if args.exclude_file: exclude_files.update(args.exclude_file)

    allowed_static = set(DEFAULT_ALLOWED_STATIC_SUBDIRS)
    if args.allow_static: allowed_static.update(args.allow_static)

    use_cache = not args.no_cache
    clear_cache = bool(args.clear_cache)
    cache_file = os.path.join(args.root, args.cache_file) if not os.path.isabs(args.cache_file) else args.cache_file

    print(f"Counting lines in: {os.path.abspath(args.root)}")
    
    # Pre-fetch valid files to pass down for global cleanup
    excl_stats = ExcludeStats()
    files_to_process_global = list(fast_walk(args.root, extensions, exclude_dirs, exclude_files, allowed_static, False, excl_stats))

    total, by_type, final_excl_stats, conn, cache_dict = process(
        root_dir=args.root,
        mode=args.mode,
        extensions=extensions,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
        allowed_static_subdirs=allowed_static,
        cache_path=cache_file,
        use_cache=use_cache,
        clear_cache=clear_cache,
        show_top=not args.no_top,
        show_excluded_stats=not args.no_excluded_stats,
    )

    summarize_excluded_lines(
        excl_stats=final_excl_stats,
        mode=args.mode,
        extensions=extensions,
        conn=conn,
        cache_dict=cache_dict,
        use_cache=use_cache,
        which=args.excluded_lines,
        limit=max(1, args.excluded_limit),
        show_progress=not args.no_progress,
    )

if __name__ == "__main__":
    main()