"""Prueba automatizada de fronteras hexagonales (Constitución Art. 1.2, 2.1, 2.4 y 3.5).

`typing.Protocol` no valida en ejecución; esta prueba inspecciona por AST las
importaciones de `src/domain/` y `src/application/`.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, Set, Tuple

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"

# Módulos prohibidos en ambas capas internas (Art. 1.2 y 3.3).
FORBIDDEN_ROOTS = {
    "json", "pathlib", "sqlite3", "argparse", "os",
    "fastapi", "starlette", "pydantic", "typer", "click", "uvicorn", "httpx",
}

# Prefijos `src.*` permitidos por capa (dirección adapters → application → domain).
ALLOWED_SRC_PREFIXES = {
    "domain": ("src.domain",),
    "application": ("src.application", "src.domain"),
}


def _imports(path: Path) -> Iterator[Tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.lineno, node.module


def _layer_files(layer: str) -> list:
    return sorted((SRC / layer).rglob("*.py"))


@pytest.mark.parametrize("layer", ["domain", "application"])
def test_capa_interna_sin_dependencias_prohibidas(layer):
    """
    Given los módulos de src/<capa>/
    When  se inspeccionan sus importaciones
    Then  no importan E/S, frameworks ni capas externas a su dirección permitida
    """
    files = _layer_files(layer)
    assert files, f"src/{layer}/ no tiene módulos"
    violations: Set[str] = set()
    for path in files:
        for lineno, module in _imports(path):
            root = module.split(".")[0]
            where = f"{path.relative_to(SRC.parent)}:{lineno} importa {module}"
            if root in FORBIDDEN_ROOTS:
                violations.add(where)
            elif root == "src" and not module.startswith(ALLOWED_SRC_PREFIXES[layer]):
                violations.add(where)
    assert not violations, "\n".join(sorted(violations))


def test_canales_de_entrada_no_conocen_persistencia():
    """
    Given los módulos de src/adapters/inbound/
    When  se inspeccionan sus importaciones
    Then  no importan sqlite3 ni adaptadores de salida: solo la raíz de composición
          conoce implementaciones concretas (Art. 2.8; complemento AST de Ruff, IV.5)
    """
    violations = []
    for path in sorted((SRC / "adapters" / "inbound").rglob("*.py")):
        for lineno, module in _imports(path):
            if module.split(".")[0] == "sqlite3" or module.startswith("src.adapters.outbound"):
                violations.append(f"{path.relative_to(SRC.parent)}:{lineno} importa {module}")
    assert not violations, "\n".join(violations)


def test_dominio_no_lee_el_reloj():
    """
    Given los módulos de src/domain/
    When  se buscan llamadas a now()/today()/utcnow()
    Then  no existe ninguna: el tiempo se inyecta (Art. 1.3)
    """
    offenders = []
    for path in _layer_files("domain"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"now", "today", "utcnow"}
            ):
                offenders.append(f"{path.relative_to(SRC.parent)}:{node.lineno}")
    assert not offenders, offenders
