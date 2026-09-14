"""Testes automatizados da versão web."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import criar_aplicacao


class TestesAplicacaoWeb(unittest.TestCase):
    """Valida a API sem iniciar servidor nem alterar o banco do usuário."""

    def setUp(self):
        # Cada teste recebe um banco isolado para não depender da ordem de execução.
        self.diretorio = tempfile.TemporaryDirectory()
        self.banco = Path(self.diretorio.name) / "taskflow_web.sqlite3"
        self.aplicacao = criar_aplicacao(self.banco)
        self.aplicacao.config.update(TESTING=True)
        self.cliente = self.aplicacao.test_client()

    def tearDown(self):
        self.diretorio.cleanup()

    def test_pagina_inicial_e_saude(self):
        resposta = self.cliente.get("/")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b"TaskFlowCards", resposta.data)
        self.assertIn(b'data-module="rooms"', resposta.data)
        self.assertIn(b'data-module="students"', resposta.data)

        saude = self.cliente.get("/api/saude")
        self.assertEqual(saude.status_code, 200)
        self.assertEqual(saude.get_json()["status"], "ok")

    def test_crud_busca_e_filtro_de_salas(self):
        resposta_criacao = self.cliente.post("/api/salas", json={
            "nome": "Sala Web",
            "descricao": "Criada pela API",
            "modo": "RITMO",
            "status": "ABERTA",
        })
        self.assertEqual(resposta_criacao.status_code, 201)
        sala = resposta_criacao.get_json()["dados"]

        resposta_lista = self.cliente.get("/api/salas?busca=web&status=ABERTA")
        salas = resposta_lista.get_json()["dados"]
        self.assertEqual([item["id"] for item in salas], [sala["id"]])

        resposta_atualizacao = self.cliente.put(f"/api/salas/{sala['id']}", json={
            "nome": "Sala Web Atualizada",
            "descricao": "Nova descrição",
            "modo": "CAOS",
            "status": "FECHADA",
        })
        self.assertEqual(resposta_atualizacao.status_code, 200)
        self.assertEqual(resposta_atualizacao.get_json()["dados"]["status"], "FECHADA")

        self.assertEqual(self.cliente.delete(f"/api/salas/{sala['id']}").status_code, 204)
        self.assertEqual(self.cliente.get("/api/salas").get_json()["dados"], [])

    def test_crud_busca_e_filtro_de_alunos(self):
        resposta_criacao = self.cliente.post("/api/alunos", json={
            "nome": "Maria da Silva",
            "matricula": "WEB001",
            "email": "maria@umc.br",
            "status": "ATIVO",
        })
        self.assertEqual(resposta_criacao.status_code, 201)
        aluno = resposta_criacao.get_json()["dados"]

        resposta_lista = self.cliente.get("/api/alunos?busca=WEB001&status=ATIVO")
        self.assertEqual(resposta_lista.get_json()["dados"][0]["id"], aluno["id"])

        resposta_atualizacao = self.cliente.put(f"/api/alunos/{aluno['id']}", json={
            "nome": "Maria Souza",
            "matricula": "WEB010",
            "email": "maria.souza@umc.br",
            "status": "BLOQUEADO",
        })
        self.assertEqual(resposta_atualizacao.status_code, 200)
        self.assertEqual(
            resposta_atualizacao.get_json()["dados"]["matricula"], "WEB010"
        )

        self.assertEqual(self.cliente.delete(f"/api/alunos/{aluno['id']}").status_code, 204)
        self.assertEqual(self.cliente.get("/api/alunos").get_json()["dados"], [])

    def test_validacao_duplicidades_e_registros_inexistentes(self):
        primeira_resposta = self.cliente.post("/api/alunos", json={
            "nome": "Aluno Um",
            "matricula": "RA001",
            "email": "aluno@umc.br",
        })
        self.assertEqual(primeira_resposta.status_code, 201)

        duplicado = self.cliente.post("/api/alunos", json={
            "nome": "Aluno Dois",
            "matricula": "ra001",
            "email": "outro@umc.br",
        })
        self.assertEqual(duplicado.status_code, 400)
        self.assertIn("matrícula", duplicado.get_json()["erro"].lower())

        sala_invalida = self.cliente.post("/api/salas", json={"nome": ""})
        self.assertEqual(sala_invalida.status_code, 400)
        self.assertIn("nome", sala_invalida.get_json()["erro"].lower())

        self.assertEqual(self.cliente.get("/api/salas/99999").status_code, 404)
        self.assertEqual(self.cliente.delete("/api/alunos/99999").status_code, 404)

    def test_migracao_das_entidades_antigas_acontece_uma_vez(self):
        # Simula a estrutura da primeira versão para comprovar compatibilidade.
        conexao = sqlite3.connect(self.banco)
        try:
            conexao.executescript("""
                CREATE TABLE rooms (
                    id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT,
                    name_key TEXT UNIQUE, description TEXT, mode TEXT, status TEXT,
                    created_at TEXT, updated_at TEXT
                );
                CREATE TABLE students (
                    id INTEGER PRIMARY KEY, registration TEXT,
                    registration_key TEXT UNIQUE, name TEXT, name_key TEXT,
                    email TEXT, email_key TEXT UNIQUE, status TEXT,
                    created_at TEXT, updated_at TEXT
                );
                INSERT INTO rooms VALUES
                    (1, 'SALA0001', 'Sala Antiga', 'sala antiga', '', 'CLASSICO',
                     'ABERTA', '2026-01-01T10:00:00+00:00', '2026-01-01T10:00:00+00:00');
                INSERT INTO students VALUES
                    (1, 'RA-ANTIGO', 'ra-antigo', 'Aluno Antigo', 'aluno antigo',
                     'antigo@umc.br', 'antigo@umc.br', 'ATIVO',
                     '2026-01-01T10:00:00+00:00', '2026-01-01T10:00:00+00:00');
            """)
        finally:
            conexao.close()

        salas = self.cliente.get("/api/salas").get_json()["dados"]
        alunos = self.cliente.get("/api/alunos").get_json()["dados"]
        self.assertEqual(salas[0]["nome"], "Sala Antiga")
        self.assertEqual(alunos[0]["nome"], "Aluno Antigo")

        self.cliente.delete(f"/api/salas/{salas[0]['id']}")
        self.cliente.delete(f"/api/alunos/{alunos[0]['id']}")
        self.assertEqual(self.cliente.get("/api/salas").get_json()["dados"], [])
        self.assertEqual(self.cliente.get("/api/alunos").get_json()["dados"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
