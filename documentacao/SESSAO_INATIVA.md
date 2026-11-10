# Encerramento da sessão por inatividade

O sistema encerra a sessão autenticada após dez minutos sem atividade fora das telas de partida, exigindo uma nova autenticação. Essa medida não bloqueia a conta nem altera a senha. A interface acompanha interações de mouse, teclado, toque e rolagem e comunica atividade ao servidor. O backend verifica o tempo da sessão nas requisições protegidas.

Nas telas de treino e de sala multijogador, a interface mantém a sessão enquanto a página da partida estiver aberta. Ao navegar para outra área, volta a valer o prazo de dez minutos. A verificação da interface ocorre em intervalos de quinze segundos. Suspensão do computador, perda de conexão ou limitação de temporizadores pelo navegador podem interromper a manutenção da sessão; nesse caso poderá ser necessário entrar novamente.

O controle depende da sessão autenticada e mantém a proteção CSRF nas requisições de atividade. O fluxo de TI não faz parte desta alteração.
