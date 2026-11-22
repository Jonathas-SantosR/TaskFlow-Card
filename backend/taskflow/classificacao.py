"""Validação comum da identificação acadêmica de salas e estudantes."""

import hashlib
import json
import unicodedata

from backend.taskflow.dominio import ErroDominio

ANOS_ESCOLARES = ("6º ANO", "7º ANO", "8º ANO", "9º ANO")
PERIODOS = ("MANHÃ", "TARDE", "INTEGRAL")


def normalizar_classificacao(ano_escolar, turma, sala_escolar):
    valores = {}
    partes = []
    for campo, valor, rotulo in (
        ("ano_escolar", ano_escolar, "ano escolar"),
        ("turma", turma, "turma"),
        ("sala_escolar", sala_escolar, "período"),
    ):
        texto = unicodedata.normalize("NFC", " ".join(str(valor or "").split())).upper()
        if not 1 <= len(texto) <= 40 or not any(c.isalnum() for c in texto):
            raise ErroDominio(f"Informe {rotulo} com 1 a 40 caracteres.")
        if any(not (c.isalnum() or c in " -./º°ª()") for c in texto):
            raise ErroDominio(f"Use letras, números e separadores simples em {rotulo}.")
        valores[campo] = texto
        if campo == "ano_escolar" and texto not in ANOS_ESCOLARES:
            raise ErroDominio("Selecione um ano escolar entre o 6º e o 9º ano.")
        if campo == "sala_escolar" and texto not in PERIODOS:
            raise ErroDominio("Selecione o período: manhã, tarde ou integral.")
        texto_chave = texto.replace("º", "").replace("°", "").replace("ª", "")
        parte = "".join(
            c for c in unicodedata.normalize("NFKD", texto_chave).casefold() if c.isalnum()
        )
        if not parte:
            raise ErroDominio(f"Informe um valor válido para {rotulo}.")
        partes.append(parte)
    # JSON distingue triplas como (1, AB, C) e (1, A, BC).
    valores["chave_academica"] = hashlib.sha256(
        json.dumps(partes, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return valores


def validar_idade(idade):
    texto = str(idade).strip()
    if len(texto) > 3 or not texto.isascii() or not texto.isdigit():
        raise ErroDominio("Informe sua idade em anos completos, entre 1 e 120.")
    valor = int(texto)
    if not 1 <= valor <= 120:
        raise ErroDominio("Informe sua idade em anos completos, entre 1 e 120.")
    return valor


def validar_idade_aluno(idade):
    """Aceita somente alunos entre 10 e 15 anos completos."""
    texto = str(idade).strip()
    if len(texto) != 2 or not texto.isascii() or not texto.isdigit():
        raise ErroDominio("A idade do aluno deve estar entre 10 e 15 anos completos.")
    valor = int(texto)
    if not 10 <= valor <= 15:
        raise ErroDominio("A idade do aluno deve estar entre 10 e 15 anos completos.")
    return valor
