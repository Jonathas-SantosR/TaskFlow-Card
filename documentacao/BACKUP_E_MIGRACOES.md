# Backup local e evolução do banco

## Histórico do esquema

`banco_de_dados/migracoes.py` registra em `versoes_esquema` o número, a descrição
e a data de aplicação de cada mudança. As versões iniciais correspondem aos
campos de contas, à sequência de questões das salas e às assinaturas de auditoria.
Em bancos existentes, as rotinas verificam colunas já presentes antes de registrar
a versão; não recriam contas nem apagam partidas. A proteção de dados legados
continua verificando a necessidade de criptografia.

Novas alterações devem receber outro número, preservando as versões anteriores.
Faça backup e pare as instâncias do aplicativo antes de atualizar. Não há downgrade
automático. DDL do MySQL pode confirmar alterações implicitamente; uma falha não
significa que todo o esquema foi revertido. As etapas atuais podem ser retomadas.

## Criar backup

Pare o servidor do jogo, mantenha o MySQL ativo e execute na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m banco_de_dados.backup criar backups\taskflow-2026-11-08.zip --banco taskflowcards --usuario taskflow_app --chaves banco_de_dados\dados
```

O comando solicita a senha e usa as ferramentas `mysqldump` e `mysql` da instalação
local. Host e porta podem ser definidos por `--host` e `--porta`. Ele não substitui
um ZIP existente. O pacote contém o dump SQL e os quatro arquivos de chaves e
sessão. A chave do Gemini não é incluída: mantenha sua configuração separada.

O ZIP não é criptografado e contém material privado. Armazene-o em local de acesso
restrito, fora do Git e da distribuição do projeto. O manifesto SHA-256 detecta
corrupção acidental; não comprova autoria de um arquivo recebido de terceiros.
Restaure somente backups confiáveis.

## Restaurar e verificar

Use outro nome de banco e uma pasta vazia, mantendo o original intacto:

```powershell
.\.venv\Scripts\python.exe -m banco_de_dados.backup restaurar backups\taskflow-2026-11-08.zip --banco taskflow_restaurado --usuario taskflow_app --chaves backups\chaves-restauradas
```

A restauração recusa banco com tabelas ou pasta de chaves com arquivos. Uma falha
durante a importação pode deixar tabelas parciais no banco de destino; não utilize
esse banco até revisar o erro. Faça uma nova tentativa em outro destino vazio.

Para passar a usar o banco restaurado, com o jogo parado, preserve a pasta atual
de chaves em um backup restrito, coloque os quatro arquivos restaurados em
`banco_de_dados/dados` e informe o novo banco no inicializador. Não misture chaves
de bancos diferentes. Confirme login, nomes legíveis, resultados e integridade da
auditoria antes de considerar a recuperação concluída.

A validação automatizada cria um professor fictício, gera o backup, restaura em
outro MySQL vazio e verifica autenticação, descriptografia e auditoria. O uso deste
procedimento não altera os perfis e as permissões de professor e aluno.
