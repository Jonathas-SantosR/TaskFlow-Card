from enum import Enum

from backend.taskflow.servicos.base import ServicoBase


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
    def meu_desempenho(self):
        aluno = self._aluno()
        return self.repositorio.desempenho_aluno(aluno.id)

    def desempenho_turma(self):
        self._professor()
        alunos = {aluno.id: aluno for aluno in self.repositorio.listar_alunos()}
        resultados = []
        for linha in self.repositorio.listar_desempenho_turma():
            aluno = alunos.get(linha["aluno_id"])
            if aluno is None:
                continue
            desempenho = self.repositorio.desempenho_aluno(aluno.id)
            resultados.append((aluno, desempenho))
        return resultados

    def dashboard_pedagogica(self):
        self._professor()
        dados = {linha["aluno_id"]: linha for linha in self.repositorio.listar_desempenho_turma()}
        contagem = {faixa: 0 for faixa in FaixaDesempenho}
        alunos = []
        for aluno in self.repositorio.listar_alunos():
            registro = dados.get(aluno.id, {})
            total = int(registro.get("total", 0))
            acertos = int(registro.get("acertos", 0))
            taxa = 100 * acertos / total if total else 0
            faixa = FaixaDesempenho.classificar(total, acertos)
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
                }
            )
        alunos.sort(key=lambda aluno: (-aluno["total"], aluno["nome"].casefold()))
        respostas = sum(aluno["total"] for aluno in alunos)
        acertos = sum(aluno["acertos"] for aluno in alunos)
        participantes = sum(aluno["total"] > 0 for aluno in alunos)
        return {
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
