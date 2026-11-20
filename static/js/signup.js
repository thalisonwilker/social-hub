/* Cadastro (spec 0013): validação no navegador, checklist da senha e habilitação de "Criar conta".
 * As regras espelham apps/accounts/validators.py; o servidor sempre revalida (AC-5). Sem consultas ao servidor. */
(function () {
  "use strict";

  var form = document.getElementById("signup-form");
  if (!form) return;

  var submit = document.getElementById("signup-submit");
  var field = function (name) { return form.querySelector('[name="' + name + '"]'); };
  // Mesmas regras de apps/accounts/validators.py: o nome é comparado na forma NFC (spec 0015, AC-3).
  var NAME_CHARS = /^[\p{L} '’-]+$/u;
  var LETTER = /\p{L}/gu;
  // Espelho do EmailValidator do Django (dot-atom + domínio com TLD de 2+ letras) — spec 0015, AC-5.
  var EMAIL_USER = /^[-!#$%&'*+\/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+\/=?^_`{}|~0-9A-Z]+)*$/i;
  var UL = "\u00a1-\uffff";
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

  function nameError(value, emptyMessage) {
    var v = value.normalize("NFC").trim();
    if (!v) return emptyMessage;
    if (v.length > 150) return "Use no máximo 150 caracteres.";
    if (!NAME_CHARS.test(v)) return "Use apenas letras, espaços, hífen ou apóstrofo.";
    if ((v.match(LETTER) || []).length < 2) return emptyMessage;
    return "";
  }

  var PASSWORD_RULES = {
    length: function (p) { return p.length >= 8; },
    upper: function (p) { return /\p{Lu}/u.test(p); },
    digit: function (p) { return /\p{Nd}/u.test(p); },
    special: function (p) { return /[^\p{L}\p{N}\s]/u.test(p); },
  };
  var PASSWORD_MESSAGES = {
    length: "A senha precisa ter pelo menos 8 caracteres.",
    upper: "A senha precisa de pelo menos uma letra maiúscula.",
    digit: "A senha precisa de pelo menos um número.",
    special: "A senha precisa de pelo menos um caractere especial (ex.: ! @ # $ %).",
  };

  var VALIDATORS = {
    first_name: function () { return nameError(field("first_name").value, "Informe seu nome."); },
    last_name: function () { return nameError(field("last_name").value, "Informe seu sobrenome."); },
    email: function () {
      var v = field("email").value.trim();
      return emailOk(v) ? "" : "Informe um e-mail válido.";
    },
    password1: function () {
      var p = field("password1").value;
      if (!p) return "Informe uma senha.";
      return Object.keys(PASSWORD_RULES)
        .filter(function (rule) { return !PASSWORD_RULES[rule](p); })
        .map(function (rule) { return PASSWORD_MESSAGES[rule]; })
        .join(" ");
    },
    password2: function () {
      return field("password2").value && field("password2").value === field("password1").value ? "" : "As senhas não coincidem.";
    },
    accept_terms: function () {
      return field("accept_terms").checked ? "" : "Você precisa aceitar os Termos de Uso e a Política de Privacidade.";
    },
  };

  var touched = {};

  function show(name, message) {
    var input = field(name);
    var slot = form.querySelector('[data-error-for="' + name + '"]');
    if (slot) slot.textContent = message;
    // O visual de erro (borda e rótulo) vem do CSS por aria-invalid — sobrevive às re-renderizações do MUI.
    input.setAttribute("aria-invalid", message ? "true" : "false");
  }

  function updatePasswordRules() {
    var p = field("password1").value;
    Object.keys(PASSWORD_RULES).forEach(function (rule) {
      var item = form.querySelector('[data-rule="' + rule + '"]');
      if (!item) return;
      var ok = PASSWORD_RULES[rule](p);
      item.classList.toggle("text-ok", ok);
      item.classList.toggle("text-muted", !ok);
      item.querySelector("[data-rule-mark]").textContent = ok ? "✓" : "•";
    });
  }

  // AC-4: habilitado só com todos os campos válidos e o aceite marcado.
  function updateSubmit() {
    var allValid = Object.keys(VALIDATORS).every(function (name) { return VALIDATORS[name]() === ""; });
    submit.disabled = !allValid;
  }

  function validate(name) {
    if (touched[name]) show(name, VALIDATORS[name]());
  }

  Object.keys(VALIDATORS).forEach(function (name) {
    var input = field(name);
    if (!input) return;
    var isCheckbox = input.type === "checkbox";
    // AC-3: mostra o erro ao sair do campo e, depois disso, a cada digitação.
    input.addEventListener("blur", function () {
      if (isCheckbox) return;
      touched[name] = true;
      validate(name);
    });
    input.addEventListener(isCheckbox ? "change" : "input", function () {
      if (isCheckbox) touched[name] = true;
      validate(name);
      if (name === "password1") { updatePasswordRules(); validate("password2"); }
      updateSubmit();
    });
  });

  // Evita um segundo clique enquanto a página envia (a trava de idempotência no servidor cobre o resto).
  // Envio único com carregamento (spec 0015, AC-1); a trava de idempotência no servidor cobre o resto.
  function setLoading(on) {
    form.toggleAttribute("data-submitting", on);
    submit.setAttribute("aria-busy", on ? "true" : "false");
    form.querySelector("[data-loading]").classList.toggle("hidden", !on);
    form.querySelector("[data-submit-label]").textContent = on ? "Registrando…" : "Registrar";
    form.querySelectorAll("input:not([type=hidden]):not([type=checkbox])").forEach(function (el) { el.readOnly = on; });
    if (on) submit.disabled = true; else updateSubmit();
  }

  form.addEventListener("submit", function (event) {
    if (form.hasAttribute("data-submitting") || submit.disabled) { event.preventDefault(); return; }
    form.setAttribute("data-submitting", "");
    // Desabilita depois do envio já disparado (desabilitar antes cancelaria o envio do botão).
    window.setTimeout(function () { setLoading(true); }, 0);
  });

  window.addEventListener("pageshow", function (event) { if (event.persisted) setLoading(false); });

  // O botão do Google não faz nada por enquanto (AC-9).
  var google = document.querySelector("[data-google-signin]");
  if (google) google.addEventListener("click", function (event) { event.preventDefault(); });

  // Erros vindos do servidor: o campo já conta como "visitado" e ganha o visual de erro.
  Object.keys(VALIDATORS).forEach(function (name) {
    var slot = form.querySelector('[data-error-for="' + name + '"]');
    if (field(name) && slot && slot.textContent.trim()) { touched[name] = true; show(name, slot.textContent.trim()); }
  });

  updatePasswordRules();
  updateSubmit();
})();
