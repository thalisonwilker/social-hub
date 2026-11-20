/* Login (spec 0014): chave de idempotência por renderização, validação antes do envio,
 * carregamento e envio único. O servidor revalida tudo; sem JS a página funciona igual (ADR-0015). */
(function () {
  "use strict";

  var form = document.getElementById("login-form");
  if (!form) return;

  var submit = document.getElementById("login-submit");
  var field = function (name) { return form.querySelector('[name="' + name + '"]'); };
  var EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  // AC-7: um UUID novo a cada renderização; reenvios desta tentativa usam o mesmo valor.
  var keyInput = form.querySelector("[data-idempotency-key]");
  if (keyInput && window.crypto && typeof window.crypto.randomUUID === "function") {
    keyInput.value = window.crypto.randomUUID();
  }

  var VALIDATORS = {
    email: function () {
      var v = field("email").value.trim();
      return v && v.length <= 254 && EMAIL.test(v) ? "" : "Informe um e-mail válido.";
    },
    password: function () {
      return field("password").value ? "" : "Informe sua senha.";
    },
  };
  var shown = {};

  function show(name, message) {
    var slot = form.querySelector('[data-error-for="' + name + '"]');
    if (slot) slot.textContent = message;
    field(name).setAttribute("aria-invalid", message ? "true" : "false");
  }

  Object.keys(VALIDATORS).forEach(function (name) {
    var input = field(name);
    var slot = form.querySelector('[data-error-for="' + name + '"]');
    if (slot && slot.textContent.trim()) { shown[name] = true; show(name, slot.textContent.trim()); }
    input.addEventListener("input", function () { if (shown[name]) show(name, VALIDATORS[name]()); });
  });

  function setLoading(on) {
    form.toggleAttribute("data-submitting", on);
    submit.disabled = on;
    submit.setAttribute("aria-busy", on ? "true" : "false");
    form.querySelector("[data-loading]").classList.toggle("hidden", !on);
    form.querySelector("[data-submit-label]").textContent = on ? "Entrando…" : "Entrar";
    form.querySelector("[data-login-status]").textContent = on ? "Entrando…" : "";
    ["email", "password"].forEach(function (name) { field(name).readOnly = on; });
  }

  form.addEventListener("submit", function (event) {
    // AC-8: um único envio por vez.
    if (form.hasAttribute("data-submitting")) { event.preventDefault(); return; }
    // AC-3: campos inválidos não saem do navegador.
    var firstInvalid = null;
    Object.keys(VALIDATORS).forEach(function (name) {
      var message = VALIDATORS[name]();
      shown[name] = true;
      show(name, message);
      if (message && !firstInvalid) firstInvalid = field(name);
    });
    if (firstInvalid) { event.preventDefault(); firstInvalid.focus(); return; }
    var error = form.querySelector("[data-login-error]");
    if (error) error.remove();
    // Desabilita depois do envio já disparado (desabilitar antes cancelaria o envio do botão).
    window.setTimeout(function () { setLoading(true); }, 0);
  });

  // Voltar pelo histórico (bfcache) não pode deixar a tela presa em "Entrando…".
  window.addEventListener("pageshow", function (event) { if (event.persisted) setLoading(false); });

  // AC-9: Google e "Esqueci minha senha" ainda não fazem nada.
  document.querySelectorAll("[data-google-signin], [data-forgot-password]").forEach(function (el) {
    el.addEventListener("click", function (event) { event.preventDefault(); });
  });
})();
