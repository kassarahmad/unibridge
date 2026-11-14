"""The UML class diagrams (docs/uml/*.puml) must name things that exist in the code: every class, attribute,
method and module function drawn in a diagram is looked up in src/p14_search with the ast module."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UML = ROOT / "docs" / "uml"
SRC = ROOT / "src" / "p14_search"

DECLARATION = re.compile(r'^\s*(?:abstract\s+)?(class|interface|enum)\s+(?:"([^"]+)"\s+as\s+\w+|(\w+))(.*)$')
MEMBER = re.compile(r"^\s*[+\-#~]\s*(\{static\}\s*)?(\w+)\s*(\()?")


def code_index():
    """classes: name -> member names; modules: file stem -> top-level function and constant names."""
    classes: dict[str, set[str]] = {}
    modules: dict[str, set[str]] = {}
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = modules.setdefault(path.stem, set())
        names.update(n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))  # also nested (FastAPI dependencies)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
                names.update(e.id for t in node.targets if isinstance(t, ast.Tuple) for e in t.elts if isinstance(e, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, ast.ClassDef):
                members = classes.setdefault(node.name, set())
                for item in ast.walk(node):
                    if isinstance(item, ast.FunctionDef):
                        members.add(item.name)
                    elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        members.add(item.target.id)
                    elif isinstance(item, ast.Assign):
                        members.update(t.id for t in item.targets if isinstance(t, ast.Name))
                    elif isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name) and item.value.id == "self":
                        members.add(item.attr)
    return classes, modules


def diagram_elements():
    """(file, kind, name, members) for every class-like element of the class diagrams."""
    for path in sorted(UML.glob("*_class_*.puml")):
        current = None
        for line in path.read_text(encoding="utf-8").splitlines():
            m = DECLARATION.match(line)
            if m and current is None:
                keyword, quoted, plain, rest = m.groups()
                kind = "library" if "<<library>>" in rest else "module" if "<<module>>" in rest else keyword
                element = (path.name, kind, quoted or plain, [])
                yield element
                current = element if rest.rstrip().endswith("{") else None
            elif current is not None:
                if line.strip() == "}":
                    current = None
                    continue
                member = MEMBER.match(line)
                if member:
                    current[3].append(member.group(2))


def test_class_diagrams_match_the_code():
    classes, modules = code_index()
    problems, checked = [], 0
    for file, kind, name, members in list(diagram_elements()):  # list(): members are filled while the file is read
        if kind == "library" or "\\n" in name:  # external libraries and free-text boxes
            continue
        if kind == "module":
            known = modules.get(name)
        elif kind == "enum":
            known = classes.get(name)
            members = []  # literals are written without a visibility sign and are not parsed
        else:
            known = classes.get(name)
        if known is None:
            problems.append(f"{file}: {kind} {name} does not exist in src/p14_search")
            continue
        checked += 1
        for member in members:
            if member not in known and member not in ("GET", "POST"):  # routes: checked by the next test
                problems.append(f"{file}: {name}.{member} does not exist")
    assert not problems, "\n".join(problems)
    assert checked > 80  # the parser really found the diagram elements


def test_routes_in_the_api_diagram_are_the_routes_of_the_application():
    from p14_search.api.app import create_app
    from p14_search.config import Settings

    def normal(path: str) -> str:
        return re.sub(r"\{\w+\}", "{id}", path)

    app = create_app(Settings(_env_file=None), init_services=False)
    real = {(method, normal(route.path)) for route in app.routes if route.path.startswith("/v1/") for method in route.methods}
    text = (UML / "09_class_api_services.puml").read_text(encoding="utf-8")
    drawn = {(method, normal(path)) for method, path in re.findall(r"^\s*\+(GET|POST) (/v1/\S+)", text, re.M)}
    assert drawn == real


def test_every_diagram_has_a_rendered_picture_and_the_shared_style():
    sources = sorted(UML.glob("*.puml"))
    assert len(sources) == 17
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert "!include _style.iuml" in text and "$legend(" in text, path.name
        for ext in ("svg", "png"):
            assert (ROOT / "docs" / "images" / "uml" / f"{path.stem}.{ext}").exists(), f"{path.stem}.{ext}: run scripts/render_plantuml.py"
