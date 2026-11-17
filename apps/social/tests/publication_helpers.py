import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.social.images import sanitize_image
from apps.social.models import SocialAccount
from apps.social.services import publishing
from apps.social.services.meta import GraphClient

from .helpers import VALID_META_SETTINGS
from .image_helpers import make_upload


class PublicationTestMixin:
    """Mídia em diretório temporário, Graph API mockada e atalhos para criar contas/publicações."""

    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        for override in (override_settings(MEDIA_ROOT=self.media, **VALID_META_SETTINGS),):
            override.enable()
            self.addCleanup(override.disable)
        patcher = mock.patch.object(GraphClient, "publish_photo", autospec=True)
        self.publish = patcher.start()
        self.addCleanup(patcher.stop)
        self.publish.side_effect = lambda client, page_id, token, **kw: {"photo_id": "p", "post_id": f"{page_id}_77"}
        User = get_user_model()
        self.alice = User.objects.create_user("alice", password="x")
        self.bob = User.objects.create_user("bob", password="x")
        self.client.force_login(self.alice)

    def make_accounts(self, n=2, owner=None, status=SocialAccount.Status.ACTIVE, start=1):
        owner = owner or self.alice
        out = []
        for i in range(start, start + n):
            acc = SocialAccount(owner=owner, platform="facebook_page", external_id=str(i), name=f"Página {i}", status=status)
            acc.set_token(f"token-{i}")
            acc.save()
            out.append(acc)
        return out

    def make_publication(self, accounts=None, owner=None, text="Texto da publicação", send=False):
        owner = owner or self.alice
        accounts = accounts if accounts is not None else self.make_accounts(2, owner)
        publication = publishing.create_publication(owner, text, sanitize_image(make_upload()), accounts)
        if send:
            publishing.send_pending(publication)
        return publication
