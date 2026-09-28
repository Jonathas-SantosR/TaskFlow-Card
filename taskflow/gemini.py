"""Integração opcional com Google AI Studio sem expor a chave no código."""

import base64
import json
import os
import re
from urllib import error, request

from taskflow.dominio import ErroDominio


URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
URL_INTERACOES = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODELO_PADRAO = "gemini-3.5-flash-lite"
MODELO_NARRACAO_PADRAO = "gemini-3.8-flash-lite-tts"
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
NUMERO_LONGO = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){8,14}(?!\w)")
MATRICULA = re.compile(r"\b(?:ra|matr[ií]cula)\s*[:#-]?\s*[A-Za-z0-9-]{3,}\b", re.I)


class ErroGemini(RuntimeError):
    pass


class ServicoGemini:
    def __init__(self, chave=None, modelo=None, timeout=20):
        self.chave = (chave if chave is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        self.modelo = modelo or os.getenv("GEMINI_MODEL", MODELO_PADRAO)
        self.modelo_narracao = os.getenv(
            "GEMINI_TTS_MODEL", MODELO_NARRACAO_PADRAO
        )
        self.timeout = timeout

    @property
    def configurado(self):
        return bool(self.chave)

    @staticmethod
    def validar_tema(tema):
        tema = " ".join(tema.split()) if isinstance(tema, str) else ""
        if not 3 <= len(tema) <= 100:
            raise ErroDominio("O tema deve ter de 3 a 100 caracteres.")
        if EMAIL.search(tema) or NUMERO_LONGO.search(tema) or MATRICULA.search(tema):
            raise ErroDominio("Não envie e-mail, telefone, documento ou matrícula para a IA.")
        return tema

    @staticmethod
    def _validar_texto_sem_dados_pessoais(texto):
        texto = " ".join(str(texto or "").split())
        if EMAIL.search(texto) or NUMERO_LONGO.search(texto) or MATRICULA.search(texto):
            raise ErroDominio(
                "Remova e-mail, telefone, documento ou matrícula antes de usar a IA."
            )
        return texto

    def _gerar_json(self, instrucao, esquema):
        if not self.chave:
            raise ErroGemini("Configure GEMINI_API_KEY antes de usar a IA.")
        corpo = {
            "contents": [{"parts": [{"text": instrucao}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": esquema,
                "maxOutputTokens": 1600,
            },
        }
        requisicao = request.Request(
            URL.format(modelo=self.modelo),
            data=json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.chave},
            method="POST",
        )
        try:
            with request.urlopen(requisicao, timeout=self.timeout) as resposta:
                dados = json.loads(resposta.read(2_000_000))
            texto = dados["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(texto)
        except error.HTTPError as exc:
            raise ErroGemini(self._explicar_erro_http(exc)) from None
        except (error.URLError, TimeoutError, OSError):
            raise ErroGemini("Não foi possível conectar ao Google AI Studio.") from None
        except (KeyError, IndexError, TypeError, ValueError):
            raise ErroGemini("A IA retornou uma resposta inválida.") from None

    def gerar_questao(self, tema, dificuldade):
        tema = self.validar_tema(tema)
        dificuldade = str(dificuldade or "MÉDIO").upper()
        if dificuldade not in {"FÁCIL", "MÉDIO", "DIFÍCIL"}:
            raise ErroDominio("Dificuldade inválida.")
        esquema = {
            "type": "OBJECT",
            "properties": {
                "enunciado": {"type": "STRING"},
                "alternativas": {"type": "ARRAY", "items": {"type": "STRING"}},
                "indice_correto": {"type": "INTEGER"},
                "explicacao": {"type": "STRING"},
                "feedback_acerto": {"type": "STRING"},
                "feedback_erro": {"type": "STRING"},
            },
            "required": [
                "enunciado",
                "alternativas",
                "indice_correto",
                "explicacao",
                "feedback_acerto",
                "feedback_erro",
            ],
        }
        questao = self._gerar_json(
            (
                "Crie uma questão educacional de múltipla escolha em português brasileiro. "
                "Retorne quatro alternativas diferentes, índice correto entre 0 e 3, uma "
                "explicação curta e mensagens pedagógicas distintas para acerto e erro. "
                "Não use dados pessoais. "
                f"Tema: {tema}. Dificuldade: {dificuldade}."
            ),
            esquema,
        )
        return self._validar_resposta(questao)

    def adaptar_questao(self, questao, dificuldade):
        dificuldade = str(dificuldade or "").strip().upper()
        if dificuldade not in {"FÁCIL", "MÉDIO", "DIFÍCIL"}:
            raise ErroDominio("Dificuldade inválida.")
        conteudo = self._validar_texto_sem_dados_pessoais(
            " ".join(
                [
                    questao.enunciado,
                    *questao.alternativas,
                    questao.explicacao,
                ]
            )
        )
        esquema = {
            "type": "OBJECT",
            "properties": {
                "enunciado": {"type": "STRING"},
                "alternativas": {"type": "ARRAY", "items": {"type": "STRING"}},
                "indice_correto": {"type": "INTEGER"},
                "explicacao": {"type": "STRING"},
                "feedback_acerto": {"type": "STRING"},
                "feedback_erro": {"type": "STRING"},
            },
            "required": [
                "enunciado",
                "alternativas",
                "indice_correto",
                "explicacao",
                "feedback_acerto",
                "feedback_erro",
            ],
        }
        adaptada = self._gerar_json(
            (
                "Adapte a questão abaixo para o nível solicitado, preservando o tema e "
                "criando quatro alternativas. Produza explicação e feedback pedagógico "
                "para acerto e erro, sem incluir dados pessoais. "
                f"Nível: {dificuldade}. Questão original: {conteudo}"
            ),
            esquema,
        )
        return self._validar_resposta(adaptada)

    def gerar_narracao(self, questao):
        """Gera áudio WAV pela API Interactions atual do Gemini TTS."""

        if not self.chave:
            raise ErroGemini("Configure GEMINI_API_KEY antes de usar a narração.")
        texto = self._validar_texto_sem_dados_pessoais(
            ". ".join(
                [
                    questao.enunciado,
                    *[
                        f"Alternativa {letra}: {alternativa}"
                        for letra, alternativa in zip("ABCD", questao.alternativas)
                    ],
                ]
            )
        )[:1400]
        corpo = {
            "model": self.modelo_narracao,
            "input": [{
                "type": "user_input",
                "content": [{
                    "type": "text",
                    "text": texto,
                    "annotations": [{
                        "type": "speech_metadata",
                        "style": "clara, calma e adequada a estudantes brasileiros",
                    }],
                }],
            }],
            "response_format": {"type": "audio", "mime_type": "audio/wav"},
            "generation_config": {"speech_config": [{"voice": "Kore"}]},
        }
        requisicao = request.Request(
            URL_INTERACOES,
            data=json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.chave,
                "Api-Revision": "2026-05-20",
            },
            method="POST",
        )
        try:
            with request.urlopen(requisicao, timeout=max(self.timeout, 30)) as resposta:
                dados = json.loads(resposta.read(15_000_000))
            saida = self._extrair_saida_audio(dados)
            if not isinstance(saida, dict) or not saida.get("data"):
                raise KeyError("output_audio")
            audio = base64.b64decode(saida["data"], validate=True)
            tipo = str(
                saida.get("mimeType") or saida.get("mime_type") or "audio/wav"
            )
            if (
                len(audio) < 12
                or len(audio) > 12_000_000
                or (tipo == "audio/wav" and not audio.startswith(b"RIFF"))
            ):
                raise ValueError("áudio fora do limite")
            return audio, tipo
        except error.HTTPError as exc:
            raise ErroGemini(self._explicar_erro_http(exc)) from None
        except (error.URLError, TimeoutError, OSError):
            raise ErroGemini("Não foi possível conectar ao serviço de narração.") from None
        except (KeyError, TypeError, ValueError):
            raise ErroGemini("A IA não retornou um áudio válido.") from None

    @staticmethod
    def _extrair_saida_audio(dados):
        """Aceita o formato atual do generateContent e o retorno antigo."""

        if not isinstance(dados, dict):
            return None
        for candidato in dados.get("candidates", []):
            conteudo = candidato.get("content", {}) if isinstance(candidato, dict) else {}
            for parte in conteudo.get("parts", []):
                if not isinstance(parte, dict):
                    continue
                saida = parte.get("inlineData") or parte.get("inline_data")
                if isinstance(saida, dict) and saida.get("data"):
                    return saida
        saida = dados.get("output_audio")
        if isinstance(saida, dict):
            return saida
        interacao = dados.get("interaction")
        if isinstance(interacao, dict):
            return interacao.get("output_audio")
        return None

    @staticmethod
    def _explicar_erro_http(exc):
        """Traduz a resposta do provedor sem expor chave, prompt ou dados pessoais."""
        codigo = int(getattr(exc, "code", 0) or 0)
        status = ""
        motivo = ""
        try:
            corpo = json.loads(exc.read(200_000).decode("utf-8", errors="replace"))
            erro_api = corpo.get("error", {}) if isinstance(corpo, dict) else {}
            status = str(erro_api.get("status", "")).upper()
            for detalhe in erro_api.get("details", []):
                if isinstance(detalhe, dict) and detalhe.get("reason"):
                    motivo = str(detalhe["reason"]).upper()
                    break
        except (AttributeError, TypeError, ValueError, OSError):
            pass

        if codigo == 400 and motivo == "API_KEY_INVALID":
            return "A chave do Google AI Studio é inválida (HTTP 400)."
        if codigo == 400 and status == "FAILED_PRECONDITION":
            return "O Google exige faturamento ou não oferece o plano gratuito nesta região (HTTP 400)."
        if codigo == 400:
            return "A solicitação foi recusada; confira a chave e o modelo configurado (HTTP 400)."
        if codigo == 402:
            return "Os créditos da API acabaram; verifique o faturamento no Google AI Studio (HTTP 402)."
        if codigo in (401, 403):
            return f"A chave não tem permissão para usar a API (HTTP {codigo})."
        if codigo == 404:
            return "O modelo configurado não está disponível para esta chave (HTTP 404)."
        if codigo == 429:
            return "O limite de uso da API foi atingido (HTTP 429)."
        if codigo in (408, 500, 502, 503, 504):
            return f"O Google AI Studio está temporariamente indisponível (HTTP {codigo})."
        return f"A API Gemini devolveu um erro HTTP {codigo or 'desconhecido'}."

    @staticmethod
    def _validar_resposta(questao):
        if not isinstance(questao, dict):
            raise ErroGemini("A IA retornou uma questão inválida.")
        alternativas = questao.get("alternativas")
        indice = questao.get("indice_correto")
        if not isinstance(alternativas, list) or len(alternativas) != 4:
            raise ErroGemini("A IA não retornou quatro alternativas.")
        if type(indice) is not int or indice not in range(4):
            raise ErroGemini("A IA retornou um gabarito inválido.")
        textos = [questao.get("enunciado"), questao.get("explicacao"), *alternativas]
        if any(not isinstance(item, str) or not item.strip() for item in textos):
            raise ErroGemini("A IA retornou conteúdo incompleto.")
        if len({item.strip().casefold() for item in alternativas}) != 4:
            raise ErroGemini("A IA retornou alternativas repetidas.")
        return {
            "enunciado": questao["enunciado"].strip()[:500],
            "alternativas": [item.strip()[:180] for item in alternativas],
            "indice_correto": indice,
            "explicacao": questao["explicacao"].strip()[:500],
            "feedback_acerto": str(
                questao.get("feedback_acerto")
                or f"Resposta correta. {questao['explicacao']}"
            ).strip()[:500],
            "feedback_erro": str(
                questao.get("feedback_erro")
                or f"Revise este conteúdo. {questao['explicacao']}"
            ).strip()[:500],
        }
