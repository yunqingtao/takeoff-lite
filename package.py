"""Build dist/takeoff_lite-<version>.zip from src/takeoff_lite."""
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
PKG = "takeoff_lite"

VERSION = "0.1.1"
OUT_DIR = os.path.join(HERE, "dist")
OUT = os.path.join(OUT_DIR, "takeoff_lite-%s.zip" % VERSION)

SKIP_DIRS = {"__pycache__", ".git", ".idea"}
SKIP_EXT = {".pyc", ".pyo"}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    root = os.path.join(SRC, PKG)
    if not os.path.isdir(root):
        raise SystemExit("missing package dir: %s" % root)

    written = []
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in sorted(files):
                if os.path.splitext(f)[1] in SKIP_EXT:
                    continue
                full = os.path.join(base, f)
                rel = os.path.relpath(full, SRC).replace("\\", "/")
                z.write(full, rel)
                written.append(rel)

    size = os.path.getsize(OUT)
    print("wrote %s (%d bytes, %d files)" % (OUT, size, len(written)))
    for w in written:
        print("  " + w)


if __name__ == "__main__":
    main()
