"""Criptografia autenticada dos dados pessoais armazenados no banco."""

import base64
import binascii
import hashlib
import hmac
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class ErroCriptografia(RuntimeError):
    """Indica chave ausente, inválida ou incompatível com o banco."""


class CriptografiaDados:
    """Protege dados reversíveis e cria índices de busca não reversíveis."""

    PREFIXO_DADO = "enc:v1:"
    PREFIXO_INDICE = "idx:v1:"

    def __init__(self, chave):
        chave_bytes = chave.encode("ascii") if isinstance(chave, str) else chave
        try:
            self._fernet = Fernet(chave_bytes)
            material = base64.urlsafe_b64decode(chave_bytes)
        except (TypeError, ValueError, binascii.Error) as erro:
            raise ErroCriptografia("A chave de criptografia dos dados é inválida.") from erro
        self._chave_indice = hashlib.sha256(
            b"taskflow-indice-v1:" + material
        ).digest()

    @classmethod
    def carregar(cls, arquivo, chave=None, permitir_criar=True):
        """Carrega a chave externa ou cria uma chave local fora do banco."""

        definida = chave or os.getenv("TASKFLOW_DATA_KEY", "").strip()
        if definida:
            return cls(definida)

        arquivo = Path(arquivo)
        if arquivo.exists():
            return cls(arquivo.read_text(encoding="ascii").strip())
        if not permitir_criar:
            raise ErroCriptografia(
                "O banco contém dados criptografados, mas a chave não foi encontrada. "
                "Restaure o arquivo data/.data_key ou informe TASKFLOW_DATA_KEY."
            )

        arquivo.parent.mkdir(parents=True, exist_ok=True)
        chave_gerada = Fernet.generate_key()
        try:
            with arquivo.open("xb") as destino:
                destino.write(chave_gerada)
            try:
                arquivo.chmod(0o600)
            except OSError:
                pass
        except FileExistsError:
            chave_gerada = arquivo.read_bytes().strip()
        return cls(chave_gerada)

    @classmethod
    def esta_criptografado(cls, valor):
        return isinstance(valor, str) and valor.startswith(cls.PREFIXO_DADO)

    def criptografar(self, valor):
        texto = str(valor)
        token = self._fernet.encrypt(texto.encode("utf-8")).decode("ascii")
        return f"{self.PREFIXO_DADO}{token}"

    def descriptografar(self, valor):
        if not self.esta_criptografado(valor):
            return valor
        token = valor[len(self.PREFIXO_DADO):]
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as erro:
            raise ErroCriptografia(
                "Não foi possível descriptografar os dados. Confira a chave configurada."
            ) from erro

    def indice(self, valor):
        """Gera um HMAC para localizar o usuário sem guardar o login em texto puro."""

        normalizado = str(valor).strip().casefold().encode("utf-8")
        resumo = hmac.new(self._chave_indice, normalizado, hashlib.sha256).hexdigest()
        return f"{self.PREFIXO_INDICE}{resumo}"


class AssinadorAuditoria:
    """Assina eventos com Ed25519 para detectar alterações no banco de auditoria."""

    def __init__(self, chave_privada):
        self._chave_privada = chave_privada
        self._chave_publica = chave_privada.public_key()

    @classmethod
    def carregar(cls, arquivo):
        arquivo = Path(arquivo)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        if arquivo.exists():
            try:
                chave = serialization.load_pem_private_key(
                    arquivo.read_bytes(), password=None
                )
                if not isinstance(chave, Ed25519PrivateKey):
                    raise TypeError("tipo de chave incompatível")
                return cls(chave)
            except (TypeError, ValueError) as erro:
                raise ErroCriptografia(
                    "A chave de assinatura da auditoria é inválida."
                ) from erro

        chave = Ed25519PrivateKey.generate()
        privada = chave.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        publica = chave.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        try:
            with arquivo.open("xb") as destino:
                destino.write(privada)
            arquivo.with_suffix(".pub").write_bytes(publica)
            try:
                arquivo.chmod(0o600)
            except OSError:
                pass
        except FileExistsError:
            return cls.carregar(arquivo)
        return cls(chave)

    @staticmethod
    def _mensagem(campos):
        return json.dumps(
            campos,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def assinar(self, campos):
        assinatura = self._chave_privada.sign(self._mensagem(campos))
        return base64.urlsafe_b64encode(assinatura).decode("ascii")

    def verificar(self, campos, assinatura):
        if not assinatura:
            return None
        try:
            valor = base64.urlsafe_b64decode(str(assinatura).encode("ascii"))
            self._chave_publica.verify(valor, self._mensagem(campos))
            return True
        except (InvalidSignature, ValueError, TypeError, binascii.Error):
            return False
