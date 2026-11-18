/* Social Hub — criar imagem com IA na nova publicação (spec 0008).
 * Os campos da seção NÃO têm `name`: nada disso (nem a chave) vai no POST de publicar. Só o id oculto `generated_image`. */
(function () {
  "use strict";
  var box = document.getElementById("ai-image");
  var $ = function (id) { return document.getElementById(id); };
  var csrf0 = (document.querySelector('input[name="csrfmiddlewaretoken"]') || {}).value || "";
  initText(csrf0);
  if (!box) return;
  var hidden = document.querySelector('input[name="generated_image"]');
  var fileInput = document.querySelector('input[name="image"]');
  var csrf = (document.querySelector('input[name="csrfmiddlewaretoken"]') || {}).value || "";

  function say(text, bad) {
    var el = $("ai-message");
    el.textContent = text || "";
    el.className = "text-xs " + (bad ? "text-danger" : "text-muted");
  }
  function show(id, url) {
    hidden.value = id || "";
    $("ai-preview").hidden = !id;
    $("ai-empty").hidden = !!id;
    $("ai-discard").hidden = !id;
    if (id) $("ai-preview").src = url;
    override();
  }
  function override() {
    $("ai-override").hidden = !(hidden.value && fileInput && fileInput.files && fileInput.files.length);
  }
  function post(url, data) {
    var body = new URLSearchParams(data);
    return fetch(url, {
      method: "POST", credentials: "same-origin", body: body,
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/x-www-form-urlencoded" }
    }).then(function (r) {
      return r.json().catch(function () { return { ok: false, error: "Resposta inesperada do servidor." }; });
    }, function () { return { ok: false, error: "Falha de rede. Tente novamente." }; });
  }
  function keyState(key) {
    $("ai-key-state").textContent = key.own ? "· cadastrada (final ••••" + key.last4 + ")" :
      key.server ? "· usando a chave do servidor" : "· não cadastrada";
    $("ai-key-remove").hidden = !key.own;
  }

  $("ai-generate").addEventListener("click", function () {
    var btn = this;
    btn.disabled = true; say("Gerando… pode levar alguns segundos.");
    post(box.dataset.generateUrl, { prompt: $("ai-prompt").value, model: $("ai-model").value }).then(function (res) {
      btn.disabled = false;
      if (res.ok) { show(res.id, res.url); say("Imagem pronta. Ela será usada na publicação."); }
      else say(res.error || "Não foi possível gerar a imagem.", true);
    });
  });
  $("ai-key-save").addEventListener("click", function () {
    var input = $("ai-key");
    post(box.dataset.keyUrl, { api_key: input.value }).then(function (res) {
      if (res.ok) { input.value = ""; keyState(res.key); say(res.message); }
      else say(res.error, true);
    });
  });
  $("ai-key-test").addEventListener("click", function () {
    var btn = this;
    btn.disabled = true; say("Testando a chave…");
    post(box.dataset.keyTestUrl, { api_key: $("ai-key").value }).then(function (res) {
      btn.disabled = false;
      say(res.ok ? "✓ " + res.message : res.error || "Não foi possível testar a chave.", !res.ok);
    });
  });
  $("ai-key-remove").addEventListener("click", function () {
    post(box.dataset.keyRemoveUrl, {}).then(function (res) { if (res.ok) { keyState(res.key); say(res.message); } });
  });
  $("ai-discard").addEventListener("click", function () { show("", ""); say(""); });
  if (fileInput) fileInput.addEventListener("change", override);
  if (box.dataset.initialId) show(box.dataset.initialId, box.dataset.initialUrl);

  function initText(token) {
    var panel = document.getElementById("ai-text");
    if (!panel) return;
    var $t = function (id) { return document.getElementById(id); };
    var msg = $t("ai-text-message"), prompt = $t("ai-text-prompt"), select = $t("ai-text-provider");
    var target = document.querySelector('textarea[name="text"]');
    function say(t, bad) { msg.textContent = t || ""; msg.className = "mt-1 text-xs " + (bad ? "text-danger" : "text-muted"); }
    function opt() { return select.options[select.selectedIndex]; }
    function refresh() {  // modelo e estado da chave do provedor escolhido
      var o = opt();
      $t("ai-text-model").textContent = o.dataset.model;
      $t("ai-text-keylabel").textContent = o.textContent;
      $t("ai-text-key-state").textContent = o.dataset.own ? "· cadastrada (final ••••" + o.dataset.last4 + ")" :
        o.dataset.server ? "· usando a chave do servidor" : "· não cadastrada";
      $t("ai-text-key-remove").hidden = !o.dataset.own;
      try { localStorage.setItem("ai-text-provider", o.value); } catch (e) { /* armazenamento indisponível */ }
    }
    function applyKey(key) {
      var o = opt();
      o.dataset.own = key.own ? "1" : ""; o.dataset.server = key.server ? "1" : ""; o.dataset.last4 = key.last4 || "";
      refresh();
      if (o.value === "gemini" && box) keyState(key);  // mantém a seção de imagem em sincronia
    }
    function call(url, data) {
      data.provider = select.value;
      return fetch(url, {
        method: "POST", credentials: "same-origin", body: new URLSearchParams(data),
        headers: { "X-CSRFToken": token, "Content-Type": "application/x-www-form-urlencoded" }
      }).then(function (r) { return r.json(); }, function () { return { ok: false, error: "Falha de rede. Tente novamente." }; })
        .catch(function () { return { ok: false, error: "Resposta inesperada do servidor." }; });
    }
    try {
      var saved = localStorage.getItem("ai-text-provider");
      if (saved && Array.prototype.some.call(select.options, function (o) { return o.value === saved; })) select.value = saved;
    } catch (e) { /* ignora */ }
    select.addEventListener("change", function () { say(""); refresh(); });
    refresh();
    $t("ai-text-example").addEventListener("click", function () { prompt.value = panel.dataset.example; prompt.focus(); });
    $t("ai-text-generate").addEventListener("click", function () {
      var btn = this;
      if (target.value.trim() && !window.confirm("Substituir o texto atual pelo texto gerado?")) return;
      btn.disabled = true; say("Gerando… pode levar alguns segundos.");
      call(panel.dataset.textUrl, { prompt: prompt.value }).then(function (res) {
        btn.disabled = false;
        if (res.ok) { target.value = res.text; target.dispatchEvent(new Event("input", { bubbles: true })); say("Texto gerado. Revise antes de publicar."); }
        else { say(res.error || "Não foi possível gerar o texto.", true); if (res.code === "no_key") $t("ai-text-keybox").open = true; }
      });
    });
    $t("ai-text-key-test").addEventListener("click", function () {
      var btn = this; btn.disabled = true; say("Testando a chave…");
      call(panel.dataset.keyTestUrl, { api_key: $t("ai-text-key").value }).then(function (res) {
        btn.disabled = false; say(res.ok ? "✓ " + res.message : res.error || "Não foi possível testar a chave.", !res.ok);
      });
    });
    $t("ai-text-key-save").addEventListener("click", function () {
      call(panel.dataset.keyUrl, { api_key: $t("ai-text-key").value }).then(function (res) {
        if (res.ok) { $t("ai-text-key").value = ""; applyKey(res.key); say(res.message); } else say(res.error, true);
      });
    });
    $t("ai-text-key-remove").addEventListener("click", function () {
      call(panel.dataset.keyRemoveUrl, {}).then(function (res) { if (res.ok) { applyKey(res.key); say(res.message); } });
    });
  }
})();
