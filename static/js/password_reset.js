/* Recuperação de senha (spec 0016): pedido (e-mail + chave de idempotência) e nova senha.
 * Regras iguais às do cadastro (static/js/signup.js) e do servidor; o servidor sempre revalida. */
(function () {
  "use strict";

  var form = document.querySelector("[data-reset-form]");
  if (!form) return;

  var mode = form.getAttribute("data-reset-form");
  var submit = form.querySelector("[data-reset-submit]");
  var field = function (name) { return form.querySelector('[name="' + name + '"]'); };

  // E-mail: espelho do EmailValidator do Django (mesma regra do cadastro).
  var EMAIL_USER = /^[-!#$%&'*+\/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+\/=?^_`{}|~0-9A-Z]+)*$/i;
  var UL = "¡-￿";
  var EMAIL_DOMAIN = new RegExp(
    "^[a-z" + UL + "0-9](?:[a-z" + UL + "0-9-]{0,61}[a-z" + UL + "0-9])?" +
    "(?:\\.(?!-)[a-z" + UL + "0-9-]{1,63}(?<!-))*" +
    "\\.(?!-)(?:[a-z" + UL + "-]{2,63}|xn--[a-z0-9]{1,59})(?<!-)$", "i");
  function emailOk(v) {
    if (!v || v.length > 254) return false;
    var at = v.lastIndexOf("@");
    if (at < 1) return false;
    var domain = v.slice(at + 1);
    return EMAIL_USER.test(v.slice(0, at)) && (EMAIL_DOMAIN.test(domain) || domain.toLowerCase() === "localhost");
  }

  var RULES = {
    length: function (p) { return p.length >= 8; },
    upper: function (p) { return /\p{Lu}/u.test(p); },
    digit: function (p) { return /\p{Nd}/u.test(p); },
    special: function (p) { return /[^\p{L}\p{N}\s]/u.test(p); },
  };
  var RULE_MESSAGES = {
    length: "A senha precisa ter pelo menos 8 caracteres.",
    upper: "A senha precisa de pelo menos uma letra maiúscula.",
    digit: "A senha precisa de pelo menos um número.",
    special: "A senha precisa de pelo menos um caractere especial (ex.: ! @ # $ %).",
  };

  var VALIDATORS = mode === "request"
    ? {
        email: function () { return emailOk(field("email").value.trim()) ? "" : "Informe um e-mail válido."; },
      }
    : {
        password1: function () {
          var p = field("password1").value;
          if (!p) return "Informe uma senha.";
          return Object.keys(RULES).filter(function (r) { return !RULES[r](p); })
            .map(function (r) { return RULE_MESSAGES[r]; }).join(" ");
        },
        password2: function () {
          var a = field("password1").value, b = field("password2").value;
          return b && a === b ? "" : "As senhas não coincidem.";
        },
      };

  var shown = {};
  function show(name, message) {
    var slot = form.querySelector('[data-error-for="' + name + '"]');
    if (slot) slot.textContent = message;
    field(name).setAttribute("aria-invalid", message ? "true" : "false");
  }
  function allValid() {
    return Object.keys(VALIDATORS).every(function (n) { return VALIDATORS[n]() === ""; });
  }
  function updateRules() {
    var input = field("password1");
    if (!input) return;
    Object.keys(RULES).forEach(function (rule) {
      var item = form.querySelector('[data-rule="' + rule + '"]');
      if (!item) return;
      var ok = RULES[rule](input.value);
      item.classList.toggle("text-ok", ok);
      item.classList.toggle("text-muted", !ok);
      item.querySelector("[data-rule-mark]").textContent = ok ? "✓" : "•";
    });
  }
  // Nova senha (AC-9): botão só habilita com tudo válido. Pedido: valida ao enviar.
  function updateSubmit() {
    if (mode === "confirm" && !form.hasAttribute("data-submitting")) submit.disabled = !allValid();
  }

  Object.keys(VALIDATORS).forEach(function (name) {
    var input = field(name);
    var slot = form.querySelector('[data-error-for="' + name + '"]');
    if (slot && slot.textContent.trim()) { shown[name] = true; show(name, slot.textContent.trim()); }
    input.addEventListener("blur", function () { shown[name] = true; show(name, VALIDATORS[name]()); });
    input.addEventListener("input", function () {
      if (shown[name]) show(name, VALIDATORS[name]());
      if (name === "password1") { updateRules(); if (shown.password2) show("password2", VALIDATORS.password2()); }
      updateSubmit();
    });
  });

  // AC-1: um UUID por renderização; reenvios desta solicitação usam o mesmo valor.
  var keyInput = form.querySelector("[data-idempotency-key]");
  if (keyInput && window.crypto && typeof window.crypto.randomUUID === "function") {
    keyInput.value = window.crypto.randomUUID();
  }

  // AC-13: carregamento e envio único.
  var label = form.querySelector("[data-submit-label]");
  var idleText = label.textContent;
  function setLoading(on) {
    form.toggleAttribute("data-submitting", on);
    submit.setAttribute("aria-busy", on ? "true" : "false");
    form.querySelector("[data-loading]").classList.toggle("hidden", !on);
    label.textContent = on ? label.getAttribute("data-busy-label") : idleText;
    form.querySelectorAll("input:not([type=hidden])").forEach(function (el) { el.readOnly = on; });
    if (on) submit.disabled = true; else { submit.disabled = false; updateSubmit(); }
  }

  form.addEventListener("submit", function (event) {
    if (form.hasAttribute("data-submitting")) { event.preventDefault(); return; }
    var firstInvalid = null;
    Object.keys(VALIDATORS).forEach(function (name) {
      var message = VALIDATORS[name]();
      shown[name] = true;
      show(name, message);
      if (message && !firstInvalid) firstInvalid = field(name);
    });
    if (firstInvalid) { event.preventDefault(); firstInvalid.focus(); return; }
    form.setAttribute("data-submitting", "");
    window.setTimeout(function () { setLoading(true); }, 0);
  });

  window.addEventListener("pageshow", function (event) { if (event.persisted) setLoading(false); });

  updateRules();
  updateSubmit();
})();
