(() => {
  const script = document.getElementById('sessao-aba');
  const chaveAba = 'taskflowcards:sessao-aba';
  const vinculo = script.dataset.vinculo;

  function abaAutenticada() {
    try {
      return Boolean(vinculo) && sessionStorage.getItem(chaveAba) === vinculo;
    } catch (_) {
      return false;
    }
  }

  const inicio = new URLSearchParams(location.hash.slice(1)).get('iniciar-aba');
  if (inicio !== null) {
    history.replaceState(null, '', location.pathname + location.search);
    try {
      if (vinculo && inicio === vinculo) sessionStorage.setItem(chaveAba, vinculo);
    } catch (_) { /* A aba precisa aceitar armazenamento para manter a sessão. */ }
  }

  function voltarAoLogin() {
    document.body.hidden = true;
    fetch('/sessao/atividade', {method: 'POST',
      body: new URLSearchParams({csrf: script.dataset.csrf, reabrir: '1'}),
      keepalive: true})
      .finally(() => location.replace(script.dataset.login));
  }

  if (!abaAutenticada()) {
    voltarAoLogin();
    return;
  }

  document.body.hidden = false;
  window.addEventListener('pagehide', () => { document.body.hidden = true; });
  window.addEventListener('pageshow', (evento) => {
    if (!evento.persisted) return;
    if (abaAutenticada()) document.body.hidden = false;
    else voltarAoLogin();
  });

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
