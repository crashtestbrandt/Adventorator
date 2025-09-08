#!/usr/bin/env python3

import os
import argparse
import sys

def crawl_py_files(root: str) -> str:
    output_parts = []
    for dirpath, _, filenames in os.walk(root):
        for fname in sorted(filenames):
            if not fname.endswith(".py"):
                continue
            rel_path = os.path.relpath(os.path.join(dirpath, fname), root)
            header = f"# {rel_path}\n"
            output_parts.append(header)
            try:
                with open(os.path.join(dirpath, fname), "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                content = f"<<error reading file: {e}>>"
            block = f"```python\n{content}\n```\n"
            output_parts.append(block)
    return "\n".join(output_parts)

def main():
    parser = argparse.ArgumentParser(description="Recursively dump .py files as markdown.")
    parser.add_argument("directory", help="Root directory to crawl")
    args = parser.parse_args()

    root = os.path.abspath(args.directory)
    md_output = crawl_py_files(root)
    
    # Ensure UTF-8 encoding for stdout
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    else:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    
    print(md_output)

if __name__ == "__main__":
    main()
