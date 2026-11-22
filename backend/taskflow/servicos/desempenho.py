from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
import re
from zoneinfo import ZoneInfo

from backend.taskflow.dominio import MODOS_JOGO, NIVEIS_DIFICULDADE, Desempenho, ErroDominio
from backend.taskflow.servicos.base import ServicoBase


def normalizar_filtros_dashboard(valores=None):
    """Valida a seleção e converte dias de São Paulo para limites UTC."""

    valores = valores or {}
    filtros = {
        campo: str(valores.get(campo, "") or "").strip()
        for campo in ("aluno_id", "sala_id", "data_inicio", "data_fim", "bimestre", "modo",
                      "dificuldade", "situacao", "turma", "faixa")
    }
    for campo, opcoes, mensagem in (
        ("modo", MODOS_JOGO, "Modo de jogo inválido."),
        ("dificuldade", NIVEIS_DIFICULDADE, "Dificuldade inválida."),
        ("situacao", ("ATIVA", "INATIVA"), "Situação da conta inválida."),
    ):
        filtros[campo] = filtros[campo].upper()
        if filtros[campo] and filtros[campo] not in opcoes:
            raise ErroDominio(mensagem)
    if filtros["turma"] and not re.fullmatch(r"[0-9a-f]{64}", filtros["turma"]):
        raise ErroDominio("Selecione uma turma válida.")
    if filtros["faixa"] and filtros["faixa"] not in FaixaDesempenho.__members__:
        raise ErroDominio("Selecione uma faixa de desempenho válida.")
    if filtros["sala_id"]:
        if not re.fullmatch(r"[1-9][0-9]{0,18}", filtros["sala_id"]):
            raise ErroDominio("Selecione uma sala válida.")
        if int(filtros["sala_id"]) > 9_223_372_036_854_775_807:
            raise ErroDominio("Selecione uma sala válida.")
    consulta = dict(filtros)
    if filtros["sala_id"]:
        consulta["sala_id"] = int(filtros["sala_id"])
    if filtros["bimestre"]:
        correspondencia = re.fullmatch(r"(20\d{2})-([1-6])", filtros["bimestre"])
        if not correspondencia:
            raise ErroDominio("Selecione um bimestre válido.")
        ano, numero = (int(valor) for valor in correspondencia.groups())
        if ano < 2026 or ano > datetime.now(ZoneInfo("America/Sao_Paulo")).year:
            raise ErroDominio("Selecione um bimestre a partir de 2026.")
        mes_inicial = 2 * numero - 1
        consulta["data_inicio"] = date(ano, mes_inicial, 1).isoformat()
        mes_final = mes_inicial + 2
        primeiro_dia_seguinte = date(ano + (mes_final > 12), (mes_final - 1) % 12 + 1, 1)
        consulta["data_fim"] = (primeiro_dia_seguinte - timedelta(days=1)).isoformat()
        filtros["data_inicio"] = filtros["data_fim"] = ""
    if filtros["aluno_id"]:
        try:
            aluno_id = int(filtros["aluno_id"])
            if not 0 < aluno_id <= 9_223_372_036_854_775_807:
                raise ValueError
        except ValueError:
            raise ErroDominio("Selecione um aluno válido.") from None
        consulta["aluno_id"] = aluno_id
        filtros["aluno_id"] = str(aluno_id)

    datas = {}
    for campo in ("data_inicio", "data_fim"):
        valor = consulta[campo]
        if not valor:
            continue
        try:
            data = date.fromisoformat(valor)
            if data.isoformat() != valor:
                raise ValueError
            datas[campo] = data
        except ValueError:
            raise ErroDominio("Informe datas válidas no formato dia, mês e ano.") from None
    if len(datas) == 2 and datas["data_inicio"] > datas["data_fim"]:
        raise ErroDominio("A data inicial não pode ser posterior à data final.")
    if datas:
        fuso = ZoneInfo("America/Sao_Paulo")
        try:
            if "data_inicio" in datas:
                consulta["inicio_utc"] = (
                    datetime.combine(datas["data_inicio"], time.min, fuso)
                    .astimezone(timezone.utc)
                    .isoformat(timespec="seconds")
                )
            if "data_fim" in datas:
                # Limite exclusivo inclui todas as respostas do último dia local.
                consulta["fim_utc"] = (
                    datetime.combine(datas["data_fim"] + timedelta(days=1), time.min, fuso)
                    .astimezone(timezone.utc)
                    .isoformat(timespec="seconds")
                )
        except (OverflowError, ValueError):
            raise ErroDominio("O período informado está fora do intervalo permitido.") from None
    return filtros, consulta


class FaixaDesempenho(Enum):
    DESTAQUE = "Destaque (80% ou mais)"
    EM_PROGRESSO = "Em progresso (50% a 79%)"
    PRECISA_APOIO = "Precisa de apoio (abaixo de 50%)"
    SEM_RESPOSTAS = "Sem respostas"

    @classmethod
    def classificar(cls, total, acertos):
        if not total:
            return cls.SEM_RESPOSTAS
        proporcao = acertos / total
        if proporcao >= 0.8:
            return cls.DESTAQUE
        if proporcao >= 0.5:
            return cls.EM_PROGRESSO
        return cls.PRECISA_APOIO


class ServicoDesempenho(ServicoBase):
    def meu_desempenho(self, modo=None, sala_id=None):
        aluno = self._aluno()
        return self.repositorio.desempenho_aluno(aluno.id, modo=modo, sala_id=sala_id)

    def reiniciar_treino_bot(self):
        aluno = self._aluno()
        removidas = self.repositorio.reiniciar_treino_bot(aluno.id)
        self.repositorio.registrar_evento(
            aluno.perfil, "TREINO_BOT_REINICIADO", "DESEMPENHO", aluno.id, aluno.id
        )
        return removidas

    def desempenho_turma(self):
        professor = self._professor()
        alunos = {aluno.id: aluno for aluno in self.repositorio.listar_alunos(professor.id)}
        resultados = []
        for linha in self.repositorio.listar_desempenho_turma(professor_id=professor.id):
            aluno = alunos.get(linha["aluno_id"])
            if aluno is None:
                continue
            desempenho = Desempenho(int(linha["total"]), int(linha["acertos"]), int(linha["pontos"]))
            resultados.append((aluno, desempenho))
        return resultados

    def dashboard_pedagogica(self, filtros=None):
        professor = self._professor()
        filtros, consulta = normalizar_filtros_dashboard(filtros)
        cadastrados = self.repositorio.listar_alunos(professor.id)
        salas = [item["sala"] for item in self.repositorio.listar_salas_professor(professor.id)]
        salas_por_id = {sala.id: sala for sala in salas}
        sala_selecionada = salas_por_id.get(consulta.get("sala_id"))
        if filtros["sala_id"] and sala_selecionada is None:
            raise ErroDominio("Selecione uma das suas salas.")
        escolaridade = self.repositorio.listar_escolaridade_alunos()
        turmas = {
            perfil["chave_academica"]: (
                f'{perfil["ano_escolar"].capitalize()} · Turma {perfil["turma"]} · '
                f'Período {perfil["sala_escolar"].capitalize()}'
            )
            for aluno in cadastrados
            if (perfil := escolaridade.get(aluno.id)) and perfil.get("chave_academica")
        }
        dados = {
            linha["aluno_id"]: linha
            for linha in self.repositorio.listar_desempenho_turma(consulta, professor_id=professor.id)
        }
        contagem = {faixa: 0 for faixa in FaixaDesempenho}
        alunos = []
        for aluno in cadastrados:
            if filtros["aluno_id"] and str(aluno.id) != filtros["aluno_id"]:
                continue
            if filtros["situacao"] and aluno.ativo != (filtros["situacao"] == "ATIVA"):
                continue
            perfil = escolaridade.get(aluno.id)
            if filtros["turma"] and (not perfil or perfil["chave_academica"] != filtros["turma"]):
                continue
            if sala_selecionada and not (
                (perfil and perfil["chave_academica"] == sala_selecionada.chave_academica)
                or aluno.id in dados
            ):
                continue
            registro = dados.get(aluno.id, {})
            total = int(registro.get("total", 0))
            acertos = int(registro.get("acertos", 0))
            taxa = 100 * acertos / total if total else 0
            faixa = FaixaDesempenho.classificar(total, acertos)
            if filtros["faixa"] and faixa.name != filtros["faixa"]:
                continue
            contagem[faixa] += 1
            alunos.append(
                {
                    "nome": aluno.nome,
                    "ativo": aluno.ativo,
                    "total": total,
                    "acertos": acertos,
                    "erros": total - acertos,
                    "percentual": round(taxa, 1),
                    "pontos": int(registro.get("pontos", 0)),
                    "faixa": faixa.value,
                    "turma": turmas.get(perfil["chave_academica"], "Sem turma vinculada") if perfil else "Sem turma vinculada",
                }
            )
        alunos.sort(key=lambda aluno: (-aluno["total"], aluno["nome"].casefold()))
        respostas = sum(aluno["total"] for aluno in alunos)
        acertos = sum(aluno["acertos"] for aluno in alunos)
        participantes = sum(aluno["total"] > 0 for aluno in alunos)
        return {
            "filtros": filtros,
            "opcoes_bimestres": [
                (f"{ano}-{numero}", f"{ano} · {numero}º bimestre ({meses})")
                for ano in range(2026, datetime.now(ZoneInfo("America/Sao_Paulo")).year + 1)
                for numero, meses in enumerate(("jan–fev", "mar–abr", "mai–jun", "jul–ago", "set–out", "nov–dez"), 1)
            ],
            "opcoes_alunos": cadastrados,
            "opcoes_salas": salas,
            "opcoes_turmas": sorted(turmas.items(), key=lambda item: item[1].casefold()),
            "opcoes_faixas": list(FaixaDesempenho),
            "filtrado": any(filtros.values()),
            "alunos": alunos,
            "faixas": [
                {"nome": faixa.value, "total": contagem[faixa]} for faixa in FaixaDesempenho
            ],
            "total_alunos": len(alunos),
            "com_respostas": participantes,
            "respostas": respostas,
            "acertos": acertos,
            "erros": respostas - acertos,
            "participacao": round(100 * participantes / len(alunos), 1) if alunos else 0,
            "aproveitamento": round(100 * acertos / respostas, 1) if respostas else 0,
        }
