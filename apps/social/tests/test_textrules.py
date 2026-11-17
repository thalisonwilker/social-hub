from django.test import SimpleTestCase

from apps.social.textrules import THREADS_MAX_LINKS, THREADS_MAX_WEIGHT, count_unique_links, threads_weight


class ThreadsWeightTests(SimpleTestCase):
    def test_AC_15_plain_text_weighs_its_length(self):
        """AC-15: ASCII, acentos e quebras de linha valem 1 cada."""
        self.assertEqual(threads_weight("abc"), 3)
        self.assertEqual(threads_weight("ação é ótima\nnova linha"), len("ação é ótima\nnova linha"))

    def test_AC_15_emoji_are_counted_by_bytes(self):
        """AC-15: emoji fora do BMP pesa 4; símbolos do BMP, VS16 e ZWJ pesam 3."""
        self.assertEqual(threads_weight("👍"), 4)
        self.assertEqual(threads_weight("☕"), 3)
        self.assertEqual(threads_weight("❤️"), 3 + 3)            # U+2764 + VS16
        self.assertEqual(threads_weight("👨‍👩"), 4 + 3 + 4)  # sequência com ZWJ
        self.assertEqual(threads_weight("oi 👍"), 3 + 4)

    def test_AC_15_limit_boundary(self):
        """AC-15: 500 caracteres simples estão no limite; 125 emoji de 4 bytes também; 126 passam."""
        self.assertEqual(threads_weight("a" * THREADS_MAX_WEIGHT), THREADS_MAX_WEIGHT)
        self.assertEqual(threads_weight("👍" * 125), 500)
        self.assertGreater(threads_weight("👍" * 126), THREADS_MAX_WEIGHT)


class LinkCountTests(SimpleTestCase):
    def test_AC_15_counts_unique_links_only(self):
        """AC-15: repetições (com ou sem barra final, caixa, pontuação) contam uma vez."""
        text = "veja https://exemplo.com/a, e https://EXEMPLO.com/a/ e (https://exemplo.com/a)."
        self.assertEqual(count_unique_links(text), 1)

    def test_AC_15_different_links_count_separately(self):
        """AC-15: URLs diferentes (caminho ou consulta) são links diferentes."""
        text = "https://a.com/1 https://a.com/2 http://b.com https://a.com/1?x=1"
        self.assertEqual(count_unique_links(text), 4)

    def test_AC_15_text_without_links(self):
        """AC-15: texto sem http(s) não tem links."""
        self.assertEqual(count_unique_links("sem links, só texto e www.exemplo.com"), 0)

    def test_AC_15_limit_is_five(self):
        """AC-15: o limite do Threads é de 5 links únicos."""
        self.assertEqual(THREADS_MAX_LINKS, 5)
        six = " ".join(f"https://s.com/{i}" for i in range(6))
        self.assertGreater(count_unique_links(six), THREADS_MAX_LINKS)
