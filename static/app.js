document.addEventListener("submit", (evento) => {
  const formulario = evento.target;
  const mensagem = formulario.dataset.processando;
  if (mensagem) {
    const botao = formulario.querySelector("button[type='submit']");
    if (botao) {
      botao.disabled = true;
      botao.textContent = mensagem;
    }
  }
  const confirmacao = formulario.dataset.confirmar;
  if (confirmacao && !window.confirm(confirmacao)) {
    evento.preventDefault();
  }
});

async function carregarNarracao(botao, audio, url, csrf) {
  const textoOriginal = botao.textContent;
  botao.disabled = true;
  botao.textContent = "Gerando áudio…";
  try {
    const dados = new FormData();
    dados.append("csrf", csrf);
    const resposta = await fetch(url, { method: "POST", body: dados });
    if (!resposta.ok) {
      const erro = await resposta
        .json()
        .catch(() => ({ erro: "Não foi possível gerar a narração." }));
      throw new Error(erro.erro);
    }
    audio.src = URL.createObjectURL(await resposta.blob());
    audio.hidden = false;
    await audio.play();
  } catch (erro) {
    window.alert(erro.message);
  } finally {
    botao.disabled = false;
    botao.textContent = textoOriginal;
  }
}

document.querySelectorAll(".formulario-narracao").forEach((formulario) => {
  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    const botao = formulario.querySelector("button[type='submit']");
    const audio = formulario.closest(".linha-questao").querySelector(".audio-questao");
    const csrf = formulario.querySelector("[name='csrf']").value;
    carregarNarracao(botao, audio, formulario.action, csrf);
  });
});

document.querySelectorAll(".formulario-narracao-botao").forEach((botao) => {
  botao.addEventListener("click", () => {
    const formulario = botao.closest("form");
    const audio = formulario.querySelector(".audio-questao");
    carregarNarracao(botao, audio, botao.dataset.url, botao.dataset.csrf);
  });
});

const salaSincronizada = document.querySelector("[data-sala-sincronizada]");
if (salaSincronizada) {
  const urlAvanco = salaSincronizada.dataset.autoAvancar;
  if (urlAvanco) {
    let segundos = 5;
    const contagem = salaSincronizada.querySelector("[data-contagem-rodada]");
    const intervalo = window.setInterval(() => {
      segundos -= 1;
      if (contagem) contagem.textContent = `Próxima rodada em ${segundos} segundo(s)…`;
      if (segundos <= 0) window.clearInterval(intervalo);
    }, 1000);
    window.setTimeout(async () => {
      const dados = new FormData();
      dados.append("csrf", salaSincronizada.dataset.csrf);
      try {
        await fetch(urlAvanco, { method: "POST", body: dados });
      } finally {
        window.location.reload();
      }
    }, 5000);
  } else if (salaSincronizada.dataset.autoAtualizar) {
    window.setTimeout(() => window.location.reload(), 3000);
  }
}
