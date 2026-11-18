"""Spec 0008 — gerar imagem com IA (Gemini). Sem rede: `requests.post` do cliente é substituído."""
import base64
import logging
from unittest import mock

import requests
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.social.models import AiProviderKey, GeneratedImage, Publication
from apps.social.services import gemini

from .image_helpers import make_image_bytes
from .publication_helpers import PublicationTestMixin

SECRET = "AIza-SECRET-KEY-1234"
NEW = "social:post_new"
MODELS = ["gemini-test-a", "gemini-test-b"]


def ok_response(data=None, mime="image/png"):
    data = data or make_image_bytes("PNG")
    body = {"candidates": [{"content": {"parts": [{"text": "ok"}, {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}]}}]}
    return mock.Mock(status_code=200, json=lambda: body, text="")


def err_response(status, text=""):
    return mock.Mock(status_code=status, json=lambda: {}, text=text)


@override_settings(GEMINI_IMAGE_MODELS=MODELS, GEMINI_API_KEY="")
class GeminiImageTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("apps.social.services.gemini.requests.post", return_value=ok_response())
        self.post_mock = patcher.start()
        self.addCleanup(patcher.stop)
        self.page = self.make_accounts(1)[0]

    def save_key(self, key=SECRET, client=None):
        return (client or self.client).post(reverse("social:ai_key_save"), {"api_key": key})

    def generate(self, prompt="um gato", model=MODELS[0], client=None):
        return (client or self.client).post(reverse("social:ai_generate"), {"prompt": prompt, "model": model})

    # ---- AC-1 / AC-8 -----------------------------------------------------
    def test_AC_1_section_with_prompt_model_and_preview(self):
        html = self.client.get(reverse(NEW)).content.decode()
        for needle in ('id="ai-prompt"', 'id="ai-preview"', 'id="ai-model"', "Google Gemini", "md:grid-cols-2"):
            self.assertIn(needle, html)
        self.assertLess(html.index("gemini-test-a"), html.index("gemini-test-b"))  # o primeiro é o padrão
        self.assertNotIn(SECRET, html)

    @override_settings(GEMINI_IMAGE_MODELS=[])
    def test_AC_8_no_models_hides_section(self):
        self.assertNotContains(self.client.get(reverse(NEW)), 'id="ai-image"')

    def test_AC_8_unknown_model_rejected_without_call(self):
        self.save_key()
        response = self.generate(model="outro-modelo")
        self.assertEqual(response.status_code, 400)
        self.post_mock.assert_not_called()

    # ---- AC-2 ------------------------------------------------------------
    def test_AC_2_generate_calls_gemini_and_stores_sanitized_image(self):
        self.save_key()
        response = self.generate()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        item = GeneratedImage.objects.get(pk=data["id"])
        self.assertEqual(item.owner, self.alice)
        self.assertEqual(item.content_type, "image/png")
        url, kwargs = self.post_mock.call_args.args[0], self.post_mock.call_args.kwargs
        self.assertTrue(url.startswith("https://generativelanguage.googleapis.com/"))
        self.assertIn("gemini-test-a:generateContent", url)
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], SECRET)
        self.assertNotIn(SECRET, url)
        self.assertEqual(Publication.objects.count(), 0)  # nada é publicado

    def test_AC_2_invalid_prompt_makes_no_call(self):
        self.save_key()
        self.assertEqual(self.generate(prompt="  ").status_code, 400)
        self.assertEqual(self.generate(prompt="x" * 2001).status_code, 400)
        self.post_mock.assert_not_called()

    def test_AC_2_regenerate_replaces_previous(self):
        self.save_key()
        self.generate()
        self.generate()
        self.assertEqual(GeneratedImage.objects.filter(owner=self.alice).count(), 1)

    # ---- AC-3 ------------------------------------------------------------
    def do_publish(self, generated_id, **extra):
        data = {"text": "Olá", "accounts": [str(self.page.pk)], "generated_image": str(generated_id)}
        data.update(extra)
        return self.client.post(reverse(NEW), data)

    def test_AC_3_generated_image_becomes_publication_image(self):
        self.save_key()
        gid = self.generate().json()["id"]
        self.do_publish(gid)
        publication = Publication.objects.get()
        self.assertTrue(publication.has_image)
        self.assertEqual(publication.image_content_type, "image/png")

    def test_AC_3_chosen_file_wins(self):
        from .image_helpers import make_upload

        self.save_key()
        gid = self.generate().json()["id"]
        self.do_publish(gid, image=make_upload())
        self.assertEqual(Publication.objects.get().image_content_type, "image/jpeg")

    def test_AC_3_expired_or_foreign_generated_image_is_rejected(self):
        self.save_key()
        gid = self.generate().json()["id"]
        GeneratedImage.objects.filter(pk=gid).update(created_at=timezone.now() - timezone.timedelta(days=2))
        self.assertEqual(self.do_publish(gid).status_code, 200)  # reexibe o formulário com erro
        self.assertEqual(Publication.objects.count(), 0)
        other = GeneratedImage(owner=self.bob, content_type="image/png")
        other.file.save("x.png", __import__("django.core.files.base", fromlist=["ContentFile"]).ContentFile(make_image_bytes("PNG")))
        self.do_publish(other.pk)
        self.assertEqual(Publication.objects.count(), 0)

    # ---- AC-4 ------------------------------------------------------------
    def test_AC_4_key_is_encrypted_and_never_returned(self):
        response = self.save_key()
        self.assertNotIn(SECRET, response.content.decode())
        record = AiProviderKey.objects.get(owner=self.alice)
        self.assertNotIn(SECRET, record.api_key_enc)
        self.assertEqual(record.get_key(), SECRET)
        self.assertEqual(record.last4, SECRET[-4:])
        page = self.client.get(reverse(NEW)).content.decode()
        self.assertNotIn(SECRET, page)
        self.assertIn(SECRET[-4:], page)

    def test_AC_4_remove_key_and_server_fallback(self):
        self.save_key()
        self.client.post(reverse("social:ai_key_remove"))
        self.assertFalse(AiProviderKey.objects.exists())
        with override_settings(GEMINI_API_KEY="SERVER-KEY"):
            self.generate()
        self.assertEqual(self.post_mock.call_args.kwargs["headers"]["x-goog-api-key"], "SERVER-KEY")

    # ---- AC-5 ------------------------------------------------------------
    def test_AC_5_no_key_no_call(self):
        response = self.generate()
        self.assertEqual(response.json()["error"], gemini.MESSAGES["no_key"])
        self.post_mock.assert_not_called()

    # ---- AC-6 ------------------------------------------------------------
    def test_AC_6_errors_are_sanitized_by_category(self):
        self.save_key()
        cases = [
            (err_response(401), "auth"), (err_response(429), "quota"), (err_response(500), "server"),
            (err_response(400, "API_KEY_INVALID"), "auth"), (err_response(400, "x"), "rejected"),
            (mock.Mock(status_code=200, json=lambda: {"candidates": [{"content": {"parts": [{"text": "não"}]}}]}), "blocked"),
            (mock.Mock(status_code=200, json=mock.Mock(side_effect=ValueError)), "bad_response"),
            (requests.exceptions.ReadTimeout(f"{SECRET} segredo"), "timeout"),
            (requests.exceptions.ConnectionError(f"{SECRET} segredo"), "network"),
        ]
        for result, code in cases:
            with self.subTest(code=code):
                self.post_mock.side_effect = result if isinstance(result, Exception) else None
                self.post_mock.return_value = None if isinstance(result, Exception) else result
                with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
                    response = self.generate(prompt="prompt-secreto")
                self.assertEqual(response.json()["code"], code)
                blob = response.content.decode() + "".join(logs.output)
                self.assertNotIn(SECRET, blob)
                self.assertNotIn("prompt-secreto", blob)
        self.assertEqual(GeneratedImage.objects.count(), 0)

    def test_AC_6_garbage_image_is_rejected(self):
        self.save_key()
        self.post_mock.return_value = ok_response(b"nao e imagem")
        self.assertEqual(self.generate().json()["code"], "bad_image")

    # ---- AC-7 ------------------------------------------------------------
    def test_AC_7_login_required_and_isolation(self):
        self.save_key()
        gid = self.generate().json()["id"]
        self.assertEqual(self.client.get(reverse("social:ai_image", args=[gid])).status_code, 200)
        self.client.logout()
        for name, args in (("ai_generate", []), ("ai_key_save", []), ("ai_key_remove", []), ("ai_image", [gid])):
            method = self.client.get if name == "ai_image" else self.client.post
            self.assertEqual(method(reverse(f"social:{name}", args=args)).status_code, 302, name)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(reverse("social:ai_image", args=[gid])).status_code, 404)
        self.assertEqual(self.generate().json()["code"], "no_key")  # a chave da alice não vale para o bob
        self.client.post(reverse("social:ai_key_remove"))
        self.assertTrue(AiProviderKey.objects.filter(owner=self.alice).exists())

    def test_AC_7_csrf_enforced(self):
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        self.assertEqual(self.generate(client=strict).status_code, 403)
        self.assertEqual(self.save_key(client=strict).status_code, 403)


@override_settings(GEMINI_IMAGE_MODELS=MODELS, GEMINI_API_KEY="")
class GeminiKeyTestButtonTests(PublicationTestMixin, TestCase):
    """AC-4/AC-6: botão "Testar" da chave (lista modelos; não gera nem guarda nada)."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch("apps.social.services.gemini.requests.get", return_value=mock.Mock(status_code=200, text=""))
        self.get_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def test_AC_4_tests_typed_key_without_saving(self):
        response = self.client.post(reverse("social:ai_key_test"), {"api_key": SECRET})
        self.assertTrue(response.json()["ok"])
        self.assertEqual(self.get_mock.call_args.kwargs["headers"]["x-goog-api-key"], SECRET)
        self.assertNotIn(SECRET, self.get_mock.call_args.args[0])
        self.assertFalse(AiProviderKey.objects.exists())
        self.assertNotIn(SECRET, response.content.decode())

    def test_AC_4_tests_saved_key_when_field_is_empty(self):
        self.client.post(reverse("social:ai_key_save"), {"api_key": SECRET})
        self.client.post(reverse("social:ai_key_test"))
        self.assertEqual(self.get_mock.call_args.kwargs["headers"]["x-goog-api-key"], SECRET)

    def test_AC_5_no_key_makes_no_call(self):
        self.assertEqual(self.client.post(reverse("social:ai_key_test")).json()["code"], "no_key")
        self.get_mock.assert_not_called()

    def test_AC_6_invalid_key_and_network_errors_are_sanitized(self):
        self.get_mock.return_value = mock.Mock(status_code=400, text="API_KEY_INVALID")
        with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
            response = self.client.post(reverse("social:ai_key_test"), {"api_key": SECRET})
        self.assertEqual(response.json()["code"], "auth")
        self.assertNotIn(SECRET, response.content.decode() + "".join(logs.output))
        self.get_mock.side_effect = requests.exceptions.ConnectionError(SECRET)
        self.assertEqual(self.client.post(reverse("social:ai_key_test"), {"api_key": SECRET}).json()["code"], "network")

    def test_AC_7_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse("social:ai_key_test")).status_code, 302)
        self.get_mock.assert_not_called()


@override_settings(GEMINI_IMAGE_MODELS=MODELS, GEMINI_API_KEY="")
class GeminiErrorDetailTests(PublicationTestMixin, TestCase):
    def test_AC_6_quota_detail_is_shown_without_the_key(self):
        body = {"error": {"status": "RESOURCE_EXHAUSTED", "message": f"Quota exceeded, limit: 0 (chave {SECRET})"}}
        response = mock.Mock(status_code=429, text="", json=lambda: body)
        with mock.patch("apps.social.services.gemini.requests.post", return_value=response):
            self.client.post(reverse("social:ai_key_save"), {"api_key": SECRET})
            with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
                data = self.client.post(reverse("social:ai_generate"), {"prompt": "x", "model": MODELS[0]}).json()
        self.assertEqual(data["code"], "quota")
        self.assertIn("RESOURCE_EXHAUSTED", data["error"])
        self.assertIn("limit: 0", data["error"])
        self.assertNotIn(SECRET, data["error"] + "".join(logs.output))


def text_response(text="Pão quentinho! 🥖"):
    body = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return mock.Mock(status_code=200, text="", json=lambda: body)


@override_settings(GEMINI_IMAGE_MODELS=MODELS, GEMINI_API_KEY="", DEEPSEEK_API_KEY="", GEMINI_TEXT_MODEL="texto-modelo", DEEPSEEK_TEXT_MODEL="ds-modelo")
class GeminiTextTests(PublicationTestMixin, TestCase):
    """AC-9: gerar o texto da publicação com o modelo de texto padrão."""

    def setUp(self):
        super().setUp()
        self.make_accounts(1)
        patcher = mock.patch("apps.social.services.gemini.requests.post", return_value=text_response())
        self.post_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def gen(self, prompt="promoção de pão"):
        return self.client.post(reverse("social:ai_text"), {"prompt": prompt})

    def test_AC_9_panel_next_to_text_with_example_prompt(self):
        html = self.client.get(reverse(NEW)).content.decode()
        for needle in ('id="ai-text-prompt"', "Gerar texto", "Usar prompt de exemplo", "padaria", "texto-modelo", "md:grid-cols-2"):
            self.assertIn(needle, html)
        self.assertLess(html.index('name="text"'), html.index('id="ai-text-prompt"'))

    @override_settings(GEMINI_TEXT_MODEL="", DEEPSEEK_TEXT_MODEL="")
    def test_AC_9_empty_model_hides_panel(self):
        self.assertNotContains(self.client.get(reverse(NEW)), 'id="ai-text"')
        self.assertEqual(self.gen().status_code, 400)

    def test_AC_9_generates_with_default_text_model_and_shared_key(self):
        self.client.post(reverse("social:ai_key_save"), {"api_key": SECRET})
        data = self.gen().json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["text"], "Pão quentinho! 🥖")
        url, kwargs = self.post_mock.call_args.args[0], self.post_mock.call_args.kwargs
        self.assertIn("texto-modelo:generateContent", url)
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], SECRET)
        self.assertNotIn("responseModalities", str(kwargs["json"]))
        self.assertEqual(Publication.objects.count(), 0)

    def test_AC_9_no_key_empty_and_long_prompt_make_no_call(self):
        self.assertEqual(self.gen().json()["code"], "no_key")
        self.client.post(reverse("social:ai_key_save"), {"api_key": SECRET})
        self.assertEqual(self.gen("  ").status_code, 400)
        self.assertEqual(self.gen("x" * 2001).status_code, 400)
        self.post_mock.assert_not_called()

    def test_AC_9_errors_sanitized_and_text_capped(self):
        self.client.post(reverse("social:ai_key_save"), {"api_key": SECRET})
        self.post_mock.return_value = mock.Mock(status_code=429, text="", json=lambda: {"error": {"status": "RESOURCE_EXHAUSTED", "message": f"limit 0 {SECRET}"}})
        with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
            data = self.gen("prompt-secreto").json()
        self.assertEqual(data["code"], "quota")
        self.assertNotIn(SECRET, data["error"] + "".join(logs.output))
        self.assertNotIn("prompt-secreto", "".join(logs.output))
        self.post_mock.return_value = mock.Mock(status_code=200, text="", json=lambda: {"candidates": []})
        self.assertEqual(self.gen().json()["code"], "blocked_text")
        with override_settings(PUBLICATION_MAX_TEXT_LENGTH=10):
            self.post_mock.return_value = text_response("a" * 50)
            self.assertEqual(len(self.gen().json()["text"]), 10)

    def test_AC_9_login_required(self):
        self.client.logout()
        self.assertEqual(self.gen().status_code, 302)


DS_KEY = "sk-deepseek-SECRET-5678"


def ds_response(text="Pão quentinho!"):
    return mock.Mock(status_code=200, text="", json=lambda: {"choices": [{"message": {"content": text}}]})


@override_settings(GEMINI_IMAGE_MODELS=MODELS, GEMINI_API_KEY="", DEEPSEEK_API_KEY="", GEMINI_TEXT_MODEL="texto-modelo", DEEPSEEK_TEXT_MODEL="ds-modelo")
class DeepSeekTextTests(PublicationTestMixin, TestCase):
    """AC-9: provedor de texto selecionável (Google Gemini ou DeepSeek), com chave própria por provedor."""

    def setUp(self):
        super().setUp()
        self.make_accounts(1)
        patcher = mock.patch("apps.social.services.deepseek.requests.post", return_value=ds_response())
        self.post_mock = patcher.start()
        self.addCleanup(patcher.stop)
        getter = mock.patch("apps.social.services.deepseek.requests.get", return_value=mock.Mock(status_code=200, text=""))
        self.get_mock = getter.start()
        self.addCleanup(getter.stop)

    def save(self, key=DS_KEY, provider="deepseek"):
        return self.client.post(reverse("social:ai_key_save"), {"api_key": key, "provider": provider})

    def gen(self, provider="deepseek", prompt="promoção"):
        return self.client.post(reverse("social:ai_text"), {"prompt": prompt, "provider": provider})

    def test_AC_9_selector_lists_both_providers(self):
        html = self.client.get(reverse(NEW)).content.decode()
        self.assertIn('id="ai-text-provider"', html)
        self.assertIn("Google Gemini", html)
        self.assertIn("DeepSeek", html)
        self.assertIn('data-model="ds-modelo"', html)

    @override_settings(DEEPSEEK_TEXT_MODEL="")
    def test_AC_9_deepseek_can_be_disabled(self):
        self.assertNotIn("DeepSeek", self.client.get(reverse(NEW)).content.decode())
        self.assertEqual(self.gen().json()["code"], "disabled")

    def test_AC_9_deepseek_generates_with_its_own_key(self):
        self.save()
        self.save(key=SECRET, provider="gemini")
        data = self.gen().json()
        self.assertEqual(data["text"], "Pão quentinho!")
        url, kwargs = self.post_mock.call_args.args[0], self.post_mock.call_args.kwargs
        self.assertEqual(url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {DS_KEY}")
        self.assertEqual(kwargs["json"]["model"], "ds-modelo")
        self.assertNotIn(DS_KEY, url)
        self.assertEqual(AiProviderKey.objects.filter(owner=self.alice).count(), 2)  # uma chave por provedor
        self.assertNotIn(DS_KEY, AiProviderKey.objects.get(provider="deepseek").api_key_enc)

    def test_AC_9_keys_are_per_provider(self):
        self.save(key=SECRET, provider="gemini")  # só a chave do Gemini
        response = self.gen()
        self.assertEqual(response.json()["code"], "no_key")
        self.assertIn("DeepSeek", response.json()["error"])
        self.post_mock.assert_not_called()
        self.client.post(reverse("social:ai_key_remove"), {"provider": "deepseek"})
        self.assertTrue(AiProviderKey.objects.filter(provider="gemini").exists())

    def test_AC_9_unknown_provider_falls_back_to_gemini(self):
        self.save(key=SECRET, provider="gemini")
        with mock.patch("apps.social.services.gemini.requests.post", return_value=text_response()) as gem:
            self.assertTrue(self.gen(provider="evil").json()["ok"])
        gem.assert_called_once()
        self.post_mock.assert_not_called()

    def test_AC_9_deepseek_errors_are_sanitized(self):
        self.save()
        cases = [(401, "auth"), (402, "balance"), (429, "quota"), (500, "server")]
        for status, code in cases:
            with self.subTest(status=status):
                self.post_mock.return_value = mock.Mock(status_code=status, text="", json=lambda: {"error": {"message": f"x {DS_KEY}"}})
                with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
                    data = self.gen(prompt="prompt-secreto").json()
                self.assertEqual(data["code"], code)
                self.assertNotIn(DS_KEY, data["error"] + "".join(logs.output))
                self.assertNotIn("prompt-secreto", "".join(logs.output))
                self.assertIn("DeepSeek", data["error"])

    def test_AC_9_deepseek_key_test_button(self):
        data = self.client.post(reverse("social:ai_key_test"), {"api_key": DS_KEY, "provider": "deepseek"}).json()
        self.assertTrue(data["ok"])
        self.assertEqual(self.get_mock.call_args.args[0], "https://api.deepseek.com/models")
        self.assertEqual(self.get_mock.call_args.kwargs["headers"]["Authorization"], f"Bearer {DS_KEY}")
        self.assertFalse(AiProviderKey.objects.exists())

    def test_AC_9_isolation_between_users(self):
        self.save()
        self.client.force_login(self.bob)
        self.assertEqual(self.gen().json()["code"], "no_key")
