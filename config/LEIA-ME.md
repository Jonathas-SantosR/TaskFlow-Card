# Configuracoes locais

## Conexao MySQL

O INICIAR.bat permite salvar servidor, porta, banco, usuario e senha em `mysql-config.json` nesta pasta. O arquivo e criado somente se a pessoa escolher salvar. Sem ele, os campos sao solicitados normalmente.

Nas proximas aberturas: Enter reutiliza; A altera os campos (Enter mantem o valor anterior); R remove somente o arquivo de configuracao e solicita uma conexao para a sessao; N usa outra conexao apenas nesta sessao. A senha pode ser mantida ou substituida durante a alteracao. A remocao nunca apaga o banco, tabelas ou dados.

O arquivo JSON pode ser aberto no Bloco de Notas, mas prefira alterar pelo inicializador para evitar erros de formato. A senha fica em texto legivel, sem dependencia do usuario Windows. O arquivo e ignorado pelo Git e nao fica acessivel pelo navegador. Antes de compartilhar um ZIP ou copia da pasta, retire `mysql-config.json` e `gemini-key.txt`. Nao distribua credenciais pessoais; cada pessoa informa as suas. A existencia do arquivo nao garante conexao: o MySQL precisa estar iniciado e aceitar essas credenciais.

## Chave Gemini

O projeto distribuido inclui `gemini-key.exemplo.txt` vazio. A chave pessoal fica em `gemini-key.txt`, ignorado pelo Git. Quem baixar o repositorio inicia sem chave e cadastra a sua pelo inicializador. Nao preencha o arquivo de exemplo.

Ao iniciar pelo INICIAR.bat, informe a chave quando solicitado. O inicializador cria `gemini-key.txt` nesta pasta e procura esse arquivo nas proximas inicializacoes. Pressione Enter para reutilizar; A para alterar; R para remover; N para iniciar sem Gemini apenas naquela sessao.

O arquivo pode ser editado pelo Bloco de Notas. Deve conter somente a chave, em uma linha, sem aspas. Se estiver ausente ou vazio, o inicializador oferece o cadastro novamente.

A chave fica em texto legivel e nao depende do usuario do Windows. O arquivo esta no .gitignore. Ao compartilhar o projeto por ZIP ou outro meio, retire gemini-key.txt para que cada pessoa cadastre a propria chave. Encontrar o arquivo nao confirma a validade da chave no Google; isso e verificado ao utilizar a API.
