// Teste do polling (static/js/poll.js) com relógio e fetch falsos: `node scripts/test-poll.mjs` (spec 0007, AC-13).
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const poll = createRequire(import.meta.url)("../static/js/poll.js");

const state = (targets, done = false) => ({ targets: targets.map(([id, status]) => ({ id, status })), done });

function harness(responses, overrides = {}) {
  const calls = { fetch: [], reload: 0, timers: [] };
  let queue = [...responses];
  const options = {
    url: "/publicacoes/1/estado/",
    signature: "1:pending|2:sending",
    intervalMs: 3000,
    fetchFn: (url) => {
      calls.fetch.push(url);
      const next = queue.shift();
      return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
    },
    reload: () => { calls.reload += 1; },
    setTimeoutFn: (fn, ms) => { calls.timers.push({ fn, ms, cancelled: false }); return calls.timers.length - 1; },
    clearTimeoutFn: (id) => { calls.timers[id].cancelled = true; },
    ...overrides,
  };
  const handle = poll.start(options);
  // roda o próximo timer pendente e espera as promessas
  const runNext = async () => {
    const timer = calls.timers.filter((t) => !t.cancelled && !t.done).shift();
    if (!timer) return false;
    timer.done = true;
    timer.fn();
    await new Promise((resolve) => setImmediate(resolve));
    return true;
  };
  return { calls, handle, runNext };
}

// 1) a assinatura é "id:estado" na ordem do servidor
assert.equal(poll.signature(state([[1, "pending"], [2, "sending"]])), "1:pending|2:sending");
assert.equal(poll.signature({}), "");

// 2) agenda a primeira consulta em 3 s e continua enquanto nada muda
{
  const h = harness([state([[1, "pending"], [2, "sending"]]), state([[1, "pending"], [2, "sending"]])]);
  assert.equal(h.calls.timers.length, 1);
  assert.equal(h.calls.timers[0].ms, 3000);
  await h.runNext();
  assert.equal(h.calls.fetch.length, 1);
  assert.equal(h.calls.reload, 0);
  assert.equal(h.calls.timers.length, 2, "agendou a próxima consulta");
  await h.runNext();
  assert.equal(h.calls.fetch.length, 2);
  assert.equal(h.calls.reload, 0);
}

// 3) quando o conjunto de estados muda, recarrega UMA vez e para
{
  const h = harness([state([[1, "published"], [2, "sending"]])]);
  await h.runNext();
  assert.equal(h.calls.reload, 1);
  assert.equal(h.calls.timers.length, 1, "não agenda mais nada depois de recarregar");
  assert.equal(await h.runNext(), false);
}

// 4) quando tudo termina (done) sem mudança de assinatura, para sem recarregar
{
  const h = harness([state([[1, "pending"], [2, "sending"]], true)]);
  await h.runNext();
  assert.equal(h.calls.reload, 0);
  assert.equal(await h.runNext(), false);
}

// 5) done com assinatura diferente: recarrega (a tela mostra o resultado final) e para
{
  const h = harness([state([[1, "published"], [2, "failed"]], true)]);
  await h.runNext();
  assert.equal(h.calls.reload, 1);
}

// 6) falhas seguidas: desiste depois de 5 (ex.: sessão expirada); um sucesso zera o contador
{
  const errors = Array.from({ length: 5 }, () => new Error("rede"));
  const h = harness(errors);
  for (let i = 0; i < 5; i += 1) await h.runNext();
  assert.equal(h.calls.fetch.length, 5);
  assert.equal(await h.runNext(), false, "parou depois de 5 falhas");
  assert.equal(h.calls.reload, 0);

  const recovering = harness([new Error("x"), new Error("x"), state([[1, "pending"], [2, "sending"]]), new Error("x"), new Error("x"), new Error("x"), new Error("x")]);
  for (let i = 0; i < 7; i += 1) await recovering.runNext();
  assert.equal(recovering.calls.fetch.length, 7, "o sucesso no meio zerou o contador de falhas");
}

// 7) aba em segundo plano: não consulta, mas continua agendando
{
  let hidden = true;
  const h = harness([state([[1, "pending"], [2, "sending"]])], { isHidden: () => hidden });
  await h.runNext();
  assert.equal(h.calls.fetch.length, 0);
  assert.equal(h.calls.timers.length, 2);
  hidden = false;
  await h.runNext();
  assert.equal(h.calls.fetch.length, 1);
}

// 8) stop() cancela o timer pendente
{
  const h = harness([]);
  h.handle.stop();
  assert.equal(h.calls.timers[0].cancelled, true);
  assert.equal(await h.runNext(), false);
}

console.log("ok: polling");
