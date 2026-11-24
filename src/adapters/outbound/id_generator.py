"""Generador de identificadores de incidente (`IncidentIdGeneratorPort`, spec 003 research §R7).

La aleatoriedad vive aquí, fuera del núcleo (Art. 1.3): el servicio solo recibe el puerto.
"""

from __future__ import annotations

import secrets


class RandomHexIdGenerator:
    """Genera `INC-` seguido de 8 dígitos hexadecimales en mayúsculas (spec 003 FR-004)."""

    def new_id(self) -> str:
        return "INC-" + secrets.token_hex(4).upper()
