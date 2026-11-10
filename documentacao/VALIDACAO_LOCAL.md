# Validação local da segunda versão

## Escopo

Esta etapa mantém o professor inicial, alunos, questões, treino, salas, dashboard,
auditoria e opções atuais de saída da conta. Não implementa automação no GitHub,
hospedagem pública, novos perfis de TI/DPO nem cadastro de vários professores.

## Ambiente e resultados

Validação em 08/11/2026, Windows, Python 3.13, MySQL 8.0.43 e Edge automatizado.
O MySQL de teste foi iniciado em localhost, porta 33070, com diretório de dados
independente. Nenhum cadastro do banco usado normalmente pelo projeto foi alterado.

| Grupo | Resultado |
| --- | --- |
| Testes locais de domínio, web, segurança e dashboard | 63 aprovados |
| Integração com MySQL real | 18 aprovados |
| Professor e dois alunos em contextos independentes do navegador | 1 aprovado |
| Ruff e verificação de formatação | Sem pendências |

Na execução padrão, os 19 testes dependentes de MySQL/navegador aparecem como
ignorados. Eles são executados separadamente com configuração explícita. Não
confundir os testes ignorados com testes aprovados.

O teste de navegador entra com três contas fictícias, cria uma sala pela tela do
professor, recebe dois alunos, responde a duas rodadas, aguarda o avanço automático
e confere quatro respostas e 100% de aproveitamento no dashboard. Também verifica
que o aluno não consegue abrir o dashboard administrativo. Ele utiliza o mesmo
servidor local; não representa teste de rede entre computadores físicos.

Os testes do Gemini usam respostas simuladas; não comprovam consumo de uma chave
real, disponibilidade do provedor ou desempenho pedagógico. A avaliação do
orientador e a revisão com usuários permanecem necessárias.

## Correção encontrada na validação

Uma resposta duplicada simultânea podia executar rollback depois de liberar o
bloqueio da conexão, interferindo em outra requisição. A transação de resposta agora
encerra ou desfaz a gravação antes de liberar esse bloqueio. O teste real confirma
uma única resposta persistida. Isso valida o processo local atual, não uma
arquitetura distribuída com vários servidores.

## Como repetir

Na raiz do projeto, com Python 3.11 ou superior:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
powershell -NoProfile -ExecutionPolicy Bypass -File tests\VERIFICAR_QUALIDADE.ps1
```

Para MySQL, use uma instância de testes e um usuário autorizado a criar/remover
bancos temporários. O roteiro não recebe o nome do banco normal da aplicação:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests\EXECUTAR_MYSQL.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests\EXECUTAR_MYSQL.ps1 -Navegador
```

O teste de navegador usa Edge instalado. As credenciais solicitadas são mantidas
somente no processo. Os bancos criados têm nomes aleatórios `taskflow_teste_<id>`
e são removidos ao terminar. Se houver interrupção abrupta, podem restar bancos de
teste; confira o nome e a origem antes de removê-los.

## Relação com os requisitos

- RF01 a RF04 e RNF01 a RNF04: cadastro, autenticação, permissões e validações.
- RF05 e RF06: questões e tratamento da integração opcional, com Gemini simulado.
- RF07 a RF10: respostas, pontos, salas e avanço das rodadas.
- RF11: indicadores calculados dos registros persistidos, sem dados ilustrativos.
- RF12 e RNF08: fluxo atual de saída e acesso aos documentos de privacidade.
- RNF05: integridade dos eventos de auditoria.
- RNF06: execução e recuperação dos dados em MySQL real.
- RNF07: execução das atividades centrais sem a API externa.

As versões em `requirements.txt` correspondem ao ambiente validado. O mínimo
declarado é Python 3.11; esta rodada não executou uma matriz de todas as versões
de Python ou de sistemas operacionais.
