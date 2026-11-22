document.addEventListener("submit", (evento) => {
  const formulario = evento.target;
  const confirmacao = formulario.dataset.confirmar;
  if (confirmacao && !window.confirm(confirmacao)) {
    evento.preventDefault();
    return;
  }
  const mensagem = formulario.dataset.processando;
  if (mensagem) {
    const botao = formulario.querySelector("button[type='submit']");
    if (botao) {
      botao.disabled = true;
      botao.textContent = mensagem;
    }
  }
});

const resultadosDashboard = document.querySelector("[data-dashboard-resultados]");
if (resultadosDashboard) {
  const estado = document.querySelector("[data-dashboard-status]");
  let atualizando = false;
  let encerrado = false;
  async function atualizarDashboard() {
    if (document.hidden || atualizando || encerrado) return;
    atualizando = true;
    try {
      const resposta = await fetch(resultadosDashboard.dataset.dashboardResultados, {
        cache: "no-store",
        redirect: "manual",
        signal: AbortSignal.timeout(8000),
      });
      if (resposta.type === "opaqueredirect" || [401, 403].includes(resposta.status)) {
        encerrado = true;
        estado.textContent = "Sessão encerrada. Entre novamente para atualizar os resultados.";
        return;
      }
      if (!resposta.ok) throw new Error("Não foi possível atualizar.");
      const conteudo = await resposta.text();
      if (resultadosDashboard.innerHTML.trim() !== conteudo.trim()) {
        const tabela = resultadosDashboard.querySelector(".dashboard-tabela");
        const rolagem = tabela?.scrollLeft || 0;
        const focoTabela = document.activeElement === tabela;
        resultadosDashboard.innerHTML = conteudo;
        const tabelaNova = resultadosDashboard.querySelector(".dashboard-tabela");
        if (focoTabela) tabelaNova?.focus({ preventScroll: true });
        if (tabelaNova) tabelaNova.scrollLeft = rolagem;
      }
      estado.textContent = "Atualização automática ativa.";
    } catch {
      estado.textContent = "Atualização interrompida. O sistema tentará novamente.";
    } finally {
      atualizando = false;
    }
  }
  window.setInterval(atualizarDashboard, 10000);
  document.addEventListener("visibilitychange", atualizarDashboard);
}

const resultadosAuditoria = document.querySelector("[data-auditoria-resultados]");
if (resultadosAuditoria) {
  const estado = document.querySelector("[data-auditoria-status]");
  let atualizando = false;
  let encerrado = false;
  async function atualizarAuditoria() {
    if (document.hidden || atualizando || encerrado) return;
    atualizando = true;
    try {
      const resposta = await fetch(resultadosAuditoria.dataset.auditoriaResultados, {
        cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(8000),
      });
      if (resposta.type === "opaqueredirect" || [401, 403].includes(resposta.status)) {
        encerrado = true;
        estado.textContent = "Sessão encerrada. Entre novamente para consultar os logs.";
        return;
      }
      if (!resposta.ok) throw new Error("Falha ao consultar logs.");
      const conteudo = await resposta.text();
      if (resultadosAuditoria.innerHTML.trim() !== conteudo.trim()) {
        const tabela = resultadosAuditoria.querySelector(".dashboard-tabela");
        const rolagem = tabela?.scrollLeft || 0;
        resultadosAuditoria.innerHTML = conteudo;
        const novaTabela = resultadosAuditoria.querySelector(".dashboard-tabela");
        if (novaTabela) novaTabela.scrollLeft = rolagem;
      }
      estado.textContent = "Logs atualizados automaticamente a cada 10 segundos.";
    } catch {
      estado.textContent = "Atualização interrompida. O sistema tentará novamente.";
    } finally {
      atualizando = false;
    }
  }
  window.setInterval(atualizarAuditoria, 10000);
  document.addEventListener("visibilitychange", atualizarAuditoria);
}

const formularioRedefinir = document.querySelector('[data-redefinir-senha]');
if (formularioRedefinir) {
  const token = new URLSearchParams(window.location.hash.slice(1)).get('token');
  if (token) {
    formularioRedefinir.elements.token.value = token;
    history.replaceState(null, '', window.location.pathname);
  }
}

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
