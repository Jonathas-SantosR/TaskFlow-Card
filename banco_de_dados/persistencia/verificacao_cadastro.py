"""Desafios de e-mail de uso unico para o cadastro web."""

import secrets
from datetime import datetime, timedelta, timezone

from backend.taskflow.dominio import ErroDominio, normalizar_gmail
from banco_de_dados.persistencia.base import RepositorioBase


class RepositorioVerificacaoCadastro(RepositorioBase):
    def __init__(self, infraestrutura, usuarios):
        super().__init__(infraestrutura)
        self.usuarios = usuarios

    def emitir(self, perfil, email):
        email = normalizar_gmail(email)
        if perfil not in {"PROFESSOR", "ALUNO"}:
            raise ErroDominio("Perfil inválido.")
        agora = datetime.now(timezone.utc)
        chave = self.criptografia.indice(email)
        with self._bloqueio, self.conexao:
            self.usuarios._validar_gmail_disponivel(email)
            linha = self.conexao.execute(
                "SELECT * FROM codigos_cadastro WHERE perfil=? AND chave_email=?",
                (perfil, chave),
            ).fetchone()
            if linha:
                enviado = datetime.fromisoformat(linha["enviado_em"])
                inicio = datetime.fromisoformat(linha["janela_inicio"])
                if agora - enviado < timedelta(seconds=60):
                    raise ErroDominio("Aguarde um minuto antes de pedir outro código.")
                dentro_da_janela = agora - inicio < timedelta(hours=1)
                quantidade = int(linha["envios_janela"]) if dentro_da_janela else 0
                if quantidade >= 5:
                    raise ErroDominio("Limite de envios atingido. Tente novamente em uma hora.")
                janela = inicio if dentro_da_janela else agora
            else:
                quantidade, janela = 0, agora
            codigo = f"{secrets.randbelow(1_000_000):06d}"
            resumo = self.criptografia.indice(f"cadastro:{perfil}:{email}:{codigo}")
            expira = (agora + timedelta(minutes=10)).isoformat()
            if linha:
                self.conexao.execute(
                    """UPDATE codigos_cadastro SET codigo_hash=?, expira_em=?, enviado_em=?,
                    janela_inicio=?, envios_janela=?, tentativas=0
                    WHERE perfil=? AND chave_email=?""",
                    (resumo, expira, agora.isoformat(), janela.isoformat(), quantidade + 1, perfil, chave),
                )
            else:
                self.conexao.execute(
                    """INSERT INTO codigos_cadastro
                    (perfil,chave_email,codigo_hash,expira_em,enviado_em,janela_inicio,envios_janela)
                    VALUES(?,?,?,?,?,?,1)""",
                    (perfil, chave, resumo, expira, agora.isoformat(), agora.isoformat()),
                )
        return email, codigo

    def conferir(self, perfil, email, codigo):
        email = normalizar_gmail(email)
        chave = self.criptografia.indice(email)
        with self._bloqueio, self.conexao:
            linha = self.conexao.execute(
                "SELECT codigo_hash,expira_em,tentativas FROM codigos_cadastro "
                "WHERE perfil=? AND chave_email=?", (perfil, chave)
            ).fetchone()
            if not linha or datetime.fromisoformat(linha["expira_em"]) <= datetime.now(timezone.utc):
                raise ErroDominio("Código expirado. Solicite outro código.")
            if int(linha["tentativas"]) >= 5:
                raise ErroDominio("Limite de tentativas atingido. Solicite outro código.")
            esperado = self.criptografia.indice(f"cadastro:{perfil}:{email}:{codigo}")
            if not secrets.compare_digest(esperado, linha["codigo_hash"]):
                self.conexao.execute(
                    "UPDATE codigos_cadastro SET tentativas=tentativas+1 "
                    "WHERE perfil=? AND chave_email=?", (perfil, chave)
                )
                valido = False
            else:
                self.conexao.execute(
                    "DELETE FROM codigos_cadastro WHERE perfil=? AND chave_email=?", (perfil, chave)
                )
                valido = True
        if not valido:
            raise ErroDominio("Código incorreto. Confira o Gmail e tente novamente.")
