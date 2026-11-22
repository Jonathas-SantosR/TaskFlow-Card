"""Entrada exclusiva da implantação web no Render."""

import os

from backend.app import criar_aplicacao


if not os.environ.get("DATABASE_URL", "").strip():
    raise RuntimeError("DATABASE_URL do PostgreSQL é obrigatória no servidor.")

app = criar_aplicacao()
