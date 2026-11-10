(() => {
  const script = document.querySelector('script[src*="sessao.js"]');
  const partida = script.dataset.partida === '1';
  let ultima = Date.now();
  let atividade = true;
  for (const evento of ['pointerdown', 'keydown', 'mousemove', 'scroll', 'touchstart']) {
    document.addEventListener(evento, () => { ultima = Date.now(); atividade = true; }, {passive: true});
  }
  setInterval(async () => {
    if (!partida && Date.now() - ultima >= 600000) {
      try {
        await fetch('/sessao/atividade', {method: 'POST',
          body: new URLSearchParams({csrf: script.dataset.csrf, expirar: '1'})});
      } finally { location.assign('/'); }
      return;
    }
    if (!partida && !atividade) return;
    atividade = false;
    try {
      const body = new URLSearchParams({csrf: script.dataset.csrf});
      const resposta = await fetch('/sessao/atividade', {method: 'POST', body,
        headers: {'X-Partida': partida ? '1' : '0'}});
      if (resposta.redirected || resposta.status === 401) location.assign('/');
    } catch (_) { /* A próxima requisição será validada pelo servidor. */ }
  }, 15000);
})();
