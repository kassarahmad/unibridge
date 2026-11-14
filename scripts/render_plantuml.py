"""Render the UML diagrams docs/uml/*.puml to docs/images/uml/*.svg and *.png with PlantUML.

Needs Java (11 or newer) and plantuml.jar. The jar is looked for in the environment variable PLANTUML_JAR, then in
tools/plantuml*.jar (tools/ is not committed). Official downloads:
- Java:     https://adoptium.net/ (Eclipse Temurin)
- PlantUML: https://github.com/plantuml/plantuml/releases (plantuml-<version>.jar) or https://plantuml.com/download
The PlantUML jar for Windows contains its own Graphviz; on Linux and macOS install Graphviz (https://graphviz.org/download/).

Usage:
    python scripts/render_plantuml.py [name ...]     (names without .puml; default: every diagram)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "uml"
OUT = ROOT / "docs" / "images" / "uml"


def find_jar() -> Path | None:
    env = os.environ.get("PLANTUML_JAR")
    if env and Path(env).is_file():
        return Path(env)
    jars = sorted((ROOT / "tools").glob("plantuml*.jar"))
    return jars[-1] if jars else None


def main() -> int:
    java, jar = shutil.which("java"), find_jar()
    if not java:
        print("Java not found. Install Eclipse Temurin 17 or newer from https://adoptium.net/ and open a new terminal.")
        return 2
    if not jar:
        print("plantuml.jar not found. Download plantuml-<version>.jar from https://github.com/plantuml/plantuml/releases\n"
              f"into {ROOT / 'tools'} (or set PLANTUML_JAR to its path).")
        return 2
    names = sys.argv[1:]
    files = [SRC / f"{n}.puml" for n in names] if names else sorted(SRC.glob("*.puml"))
    missing = [f.name for f in files if not f.exists()]
    if missing:
        print("unknown diagram(s):", ", ".join(missing))
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    for fmt in ("svg", "png"):
        cmd = [java, "-Djava.awt.headless=true", "-DPLANTUML_LIMIT_SIZE=16384", "-jar", str(jar), f"-t{fmt}", "-charset", "UTF-8",
               "-failfast2", "-nometadata", "-o", str(OUT), *map(str, files)]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        if r.returncode != 0:
            print(r.stdout, r.stderr, sep="\n")
            print(f"PlantUML failed ({fmt}).")
            return 1
    print(f"rendered {len(files)} diagram(s) to {OUT.relative_to(ROOT)} (svg + png) with {jar.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
