/* Social Hub — acompanhamento do envio em segundo plano (spec 0007).
 * Consulta GET .../estado/ a cada poucos segundos enquanto há alvo na fila ou enviando; recarrega a página quando o conjunto de
 * estados muda e PARA quando tudo terminou. A lógica é pura (testável em Node: scripts/test-poll.mjs); o DOM só liga o início. */
(function (root) {
  "use strict";

  function signature(state) {
    return ((state && state.targets) || []).map(function (t) { return t.id + ":" + t.status; }).join("|");
  }

  /* options: url, signature, intervalMs, fetchFn(url)->Promise<state>, reload(), setTimeoutFn, clearTimeoutFn, isHidden, maxErrors */
  function start(options) {
    var errors = 0;
    var stopped = false;
    var timer = null;
    var maxErrors = options.maxErrors || 5;

    function schedule() {
      timer = options.setTimeoutFn(tick, options.intervalMs);
    }

    function tick() {
      if (stopped) return;
      if (options.isHidden && options.isHidden()) { schedule(); return; }  // aba em segundo plano: não consulta
      options.fetchFn(options.url).then(function (state) {
        if (stopped) return;
        errors = 0;
        if (signature(state) !== options.signature) {  // algo mudou: a página (renderizada no servidor) é a fonte da verdade
          stopped = true;
          options.reload();
          return;
        }
        if (state.done) { stopped = true; return; }
        schedule();
      }).catch(function () {
        errors += 1;
        if (errors >= maxErrors) { stopped = true; return; }  // desiste depois de falhas seguidas (ex.: sessão expirada)
        if (!stopped) schedule();
      });
    }

    schedule();
    return {
      stop: function () {
        stopped = true;
        if (timer !== null && options.clearTimeoutFn) options.clearTimeoutFn(timer);
      }
    };
  }

  var api = { signature: signature, start: start };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; } else { root.SocialHubPoll = api; }

  if (root.document && root.fetch) {
    root.document.addEventListener("DOMContentLoaded", function () {
      var el = root.document.querySelector("[data-poll-url]");
      if (!el) return;  // sem alvo em andamento a página não traz o atributo: nenhuma consulta
      start({
        url: el.getAttribute("data-poll-url"),
        signature: el.getAttribute("data-poll-signature") || "",
        intervalMs: parseInt(el.getAttribute("data-poll-interval") || "3000", 10),
        fetchFn: function (url) {
          return root.fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } }).then(function (r) {
            if (!r.ok) throw new Error("http " + r.status);
            return r.json();
          });
        },
        reload: function () { root.location.reload(); },
        setTimeoutFn: function (fn, ms) { return root.setTimeout(fn, ms); },
        clearTimeoutFn: function (id) { root.clearTimeout(id); },
        isHidden: function () { return root.document.hidden === true; }
      });
    });
  }
})(typeof window !== "undefined" ? window : globalThis);
