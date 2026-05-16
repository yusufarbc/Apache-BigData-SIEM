# -*- coding: utf-8 -*-
"""
merge_logs.py
-------------
Belirtilen kaynak dizindeki (varsayilan: raw_data/) tum .log dosyalarini
data/ dizinine kopyalar. Ayni isimde dosyalar varsa iceriklerini birlestirir.
Islem bitince her dosyadaki satir sayisini ve genel toplami yazdirir.

Kullanim:
  python scripts/merge_logs.py              # kaynak: raw_data/
  python scripts/merge_logs.py --src log   # kaynak: log/
"""

import os
import shutil
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--src",  default="raw_data", help="Kaynak dizin")
parser.add_argument("--dest", default="data",     help="Hedef dizin")
args = parser.parse_args()

RAW_DATA = args.src
DEST_DIR = args.dest

os.makedirs(DEST_DIR, exist_ok=True)

# --- 1. Merge ---
merged = {}   # filename -> source count
errors = []

for root, dirs, files in os.walk(RAW_DATA):
    dirs.sort()   # deterministic order
    for fname in sorted(files):
        if not fname.lower().endswith(".log"):
            continue
        src = os.path.join(root, fname)
        dst = os.path.join(DEST_DIR, fname)
        try:
            if fname not in merged:
                shutil.copy2(src, dst)
                merged[fname] = 1
            else:
                # append mode (binary to preserve line endings)
                with open(dst, "ab") as fout, open(src, "rb") as fin:
                    fout.write(fin.read())
                merged[fname] += 1
        except Exception as exc:
            errors.append(f"{src}: {exc}")

# --- 2. Count lines ---
total_lines = 0
per_file = []

for fname in sorted(merged.keys()):
    count = merged[fname]
    path = os.path.join(DEST_DIR, fname)
    try:
        with open(path, "rb") as f:
            lines = f.read().count(b"\n")
    except Exception:
        lines = -1
    total_lines += max(lines, 0)
    per_file.append((fname, lines, count))

# --- 3. Report ---
COL1, COL2, COL3 = 30, 16, 16
sep = "-" * (COL1 + COL2 + COL3 + 2)

print()
print("=" * (COL1 + COL2 + COL3 + 2))
print("  LOG MERGE TAMAMLANDI")
print("=" * (COL1 + COL2 + COL3 + 2))
print(f"  data/ dizinindeki benzersiz log dosyasi: {len(merged)}")
print(f"  Atlanan dosya (hata): {len(errors)}")
print()
print(f"{'Dosya Adi':<{COL1}} {'Satir Sayisi':>{COL2}} {'Kaynak Sayisi':>{COL3}}")
print(sep)
for fname, lines, count in per_file:
    lines_str = f"{lines:,}" if lines >= 0 else "HATA"
    print(f"{fname:<{COL1}} {lines_str:>{COL2}} {count:>{COL3}}")
print(sep)
print(f"{'GENEL TOPLAM':<{COL1}} {total_lines:>{COL2},}")
print()

if errors:
    print(f"ATLANMIŞ DOSYALAR ({len(errors)} adet):")
    for e in errors[:20]:
        print(f"  {e}")
    if len(errors) > 20:
        print(f"  ... ve {len(errors) - 20} dosya daha")
