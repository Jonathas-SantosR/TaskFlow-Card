"""Proteção de senhas do protótipo sem armazenar texto puro."""

import base64
import hashlib
import hmac
import secrets

from backend.taskflow.dominio import ErroDominio

ITERACOES = 600_000


def validar_senha(senha):
    if not isinstance(senha, str) or not 12 <= len(senha) <= 128:
        raise ErroDominio("A senha deve ter de 12 a 128 caracteres.")
    return senha


def validar_codigo_recuperacao(codigo):
    """Valida o segredo usado exclusivamente na recuperação do professor."""

    if not isinstance(codigo, str) or not 12 <= len(codigo) <= 128:
        raise ErroDominio("O código de recuperação deve ter de 12 a 128 caracteres.")
    if not any(caractere.isupper() for caractere in codigo):
        raise ErroDominio("O código de recuperação deve conter pelo menos uma letra maiúscula.")
    if not any(caractere.isdigit() for caractere in codigo):
        raise ErroDominio("O código de recuperação deve conter pelo menos um número.")
    return codigo


def criar_hash(senha):
    senha = validar_senha(senha)
    sal = secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, ITERACOES)
    return "pbkdf2_sha256${}${}${}".format(
        ITERACOES,
        base64.urlsafe_b64encode(sal).decode("ascii"),
        base64.urlsafe_b64encode(derivada).decode("ascii"),
    )


def conferir_senha(senha, valor_armazenado):
    try:
        algoritmo, iteracoes, sal, esperado = str(valor_armazenado).split("$", 3)
        if algoritmo != "pbkdf2_sha256":
            return False
        derivada = hashlib.pbkdf2_hmac(
            "sha256",
            str(senha).encode("utf-8"),
            base64.urlsafe_b64decode(sal.encode("ascii")),
            int(iteracoes),
        )
        return hmac.compare_digest(base64.urlsafe_b64encode(derivada).decode("ascii"), esperado)
    except (TypeError, ValueError):
        return False
