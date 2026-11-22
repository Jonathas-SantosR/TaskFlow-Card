(() => {
  const script = document.querySelector('script[src*="sala_aluno.js"]');
  if (!script) return;
  const codigoAtual = script.dataset.codigo || '';

  async function verificarSala() {
    try {
      const resposta = await fetch(script.dataset.url, {
        cache: 'no-store', credentials: 'same-origin',
      });
      if (resposta.redirected || !resposta.ok) return;
      const dados = await resposta.json();
      if ((dados.codigo || '') !== codigoAtual) window.location.reload();
    } catch (_) {
      // A próxima consulta tentará novamente sem interromper a página.
    }
  }

  window.setInterval(verificarSala, 60000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) verificarSala();
  });
})();
