(() => {
  const script = document.querySelector('script[src*="sala_aluno.js"]');
  if (!script) return;
  const salasAtuais = JSON.stringify(JSON.parse(script.dataset.salas || '[]'));

  async function verificarSala() {
    try {
      const resposta = await fetch(script.dataset.url, {
        cache: 'no-store', credentials: 'same-origin',
      });
      if (resposta.redirected || !resposta.ok) return;
      const dados = await resposta.json();
      if (JSON.stringify(dados.salas || []) !== salasAtuais) window.location.reload();
    } catch (_) {
      // A próxima consulta tentará novamente sem interromper a página.
    }
  }

  window.setInterval(verificarSala, 60000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) verificarSala();
  });
})();
