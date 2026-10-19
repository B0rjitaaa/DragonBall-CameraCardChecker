import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from cards.bandai import normalize_card
from cards.importer import upsert_cards
from cards.models import Card, CardFingerprint
from scans.models import Scan
from vision import fingerprint as fp
from vision.preprocess import encode_jpeg

from .synthetic import make_card, make_photo

MEDIA = tempfile.mkdtemp()

BANDAI_LEADER = {
    "id": 4,
    "card_name": "Champa",
    "card_number": "BT1-001",
    "card_text": "[Auto] ...",
    "image_url": "https://files.bandai-tcg-plus.com/card_image/DB-EN/BT1/BT1-001.png",
    "card_set": "Booster Pack ～GALACTIC BATTLE～ [DBS-B01]",
    "card_config": [
        {"config_name": "Type", "value": "LEADER"},
        {"config_name": "Rarity", "value": "Rare[R]"},
        {"config_name": "Energy"},
        {"config_name": "Power", "value": "10000"},
        {"config_name": "Era", "value": "Champa Saga"},
        {"config_name": "Notes", "value": ""},
    ],
    "backcard_card_name": "God of Destruction Champa",
    "backcard_card_text": "[Auto] When this card attacks, draw 1 card.",
    "backcard_image_url": "https://files.bandai-tcg-plus.com/card_image/DB-EN/BT1/BT1-001_b.png",
    "backcard_card_config": [{"config_name": "Power", "value": "15000"}],
    "regulations": [{"id": 1, "title": "Constructed"}],
}


class NormalizeCardTests(TestCase):
    def test_bandai_record(self):
        data = normalize_card(BANDAI_LEADER)
        self.assertEqual(data["bandai_id"], 4)
        self.assertEqual(data["card_number"], "BT1-001")
        self.assertEqual(data["set_code"], "BT1")
        self.assertEqual(data["card_type"], "LEADER")
        self.assertEqual(data["rarity"], "Rare[R]")
        self.assertEqual(data["power"], "10000")
        self.assertEqual(data["cost"], "")
        self.assertEqual(data["back_name"], "God of Destruction Champa")
        self.assertTrue(data["image_back_url"].endswith("BT1-001_b.png"))
        self.assertEqual(
            data["attributes"],
            {"Era": "Champa Saga", "Back Power": "15000", "Regulations": ["Constructed"]},
        )

    def test_invalid_record(self):
        self.assertIsNone(normalize_card({"card_name": "Sin id ni número"}))

    def test_alt_arts_are_separate_cards(self):
        alt = {**BANDAI_LEADER, "id": 1088, "image_url": "https://x/BT1-001_PR.png"}
        self.assertEqual(upsert_cards([BANDAI_LEADER, alt]).created, 2)
        self.assertEqual(Card.objects.filter(card_number="BT1-001").count(), 2)

    def test_upsert_is_idempotent(self):
        upsert_cards([BANDAI_LEADER])
        renamed = {**BANDAI_LEADER, "card_name": "Champa!"}
        stats = upsert_cards([renamed])
        self.assertEqual((stats.created, stats.updated, stats.unchanged), (0, 1, 0))
        self.assertEqual(upsert_cards([renamed]).unchanged, 1)


@override_settings(MEDIA_ROOT=MEDIA, CELERY_TASK_ALWAYS_EAGER=True)
class ScanApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.cards = []
        for seed in range(10):
            card = Card.objects.create(
                bandai_id=seed + 1, card_number=f"BT1-{seed:03d}", name=f"Carta {seed}"
            )
            prints = fp.compute(make_card(seed))
            CardFingerprint.objects.create(
                card=card,
                source_url=f"https://example.com/{seed}.png",
                phash=prints.phash,
                dhash=prints.dhash,
                orb=prints.orb,
                orb_count=prints.orb_count,
            )
            self.cards.append(card)

    def test_upload_scan_identifies_card(self):
        upload = SimpleUploadedFile(
            "foto.jpg", encode_jpeg(make_photo(make_card(4))), content_type="image/jpeg"
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/scans/", {"image": upload}, format="multipart")
        self.assertEqual(response.status_code, 202)

        detail = self.client.get(f"/api/scans/{response.data['id']}/").data
        self.assertEqual(detail["status"], Scan.Status.DONE)
        self.assertEqual(detail["matched_card"]["card_number"], "BT1-004")
        self.assertFalse(detail["needs_review"])
        self.assertTrue(detail["cropped_image"])
        self.assertEqual(detail["candidates"][0]["card_number"], "BT1-004")

    def _upload(self, card_seed):
        upload = SimpleUploadedFile(
            "foto.jpg", encode_jpeg(make_photo(make_card(card_seed))), content_type="image/jpeg"
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/scans/", {"image": upload}, format="multipart")
        return self.client.get(f"/api/scans/{response.data['id']}/").data

    def test_confirm_learns_uncatalogued_printing(self):
        # Seed 99: "impresión" que no está en el catálogo (p. ej. una promo).
        first = self._upload(99)
        self.assertTrue(first["needs_review"])

        target = self.cards[3]
        response = self.client.post(
            f"/api/scans/{first['id']}/confirm/", {"card_id": target.id}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["confirmed"])
        self.assertFalse(response.data["needs_review"])
        self.assertEqual(response.data["matched_card"]["id"], target.id)
        self.assertTrue(CardFingerprint.objects.filter(card=target, face="scan").exists())

        # La siguiente foto de esa misma impresión ya se reconoce sola.
        second = self._upload(99)
        self.assertEqual(second["matched_card"]["id"], target.id)
        self.assertFalse(second["needs_review"])

    def test_confirm_rejects_unfinished_scan(self):
        scan = Scan.objects.create(source=Scan.Source.CAMERA)
        response = self.client.post(
            f"/api/scans/{scan.id}/confirm/", {"card_id": self.cards[0].id}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(CAMERA_URL="")
    def test_camera_scan_without_camera_fails_gracefully(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/scans/", {}, format="json")
        scan = Scan.objects.get(pk=response.data["id"])
        self.assertEqual(scan.source, Scan.Source.CAMERA)
        self.assertEqual(scan.status, Scan.Status.FAILED)
        self.assertIn("CAMERA_URL", scan.error)

    @override_settings(CAMERA_URL="http://camera:8080")
    def test_camera_scan_fails_when_camera_has_no_frames(self):
        with mock.patch("scans.camera.requests.get") as get:
            get.return_value.status_code = 503
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post("/api/scans/", {}, format="json")
        scan = Scan.objects.get(pk=response.data["id"])
        self.assertEqual(scan.status, Scan.Status.FAILED)
        self.assertIn("webcam desconectada", scan.error)

    @override_settings(CAMERA_URL="http://camera:8080")
    def test_camera_preview_proxies_frame(self):
        with mock.patch("scans.camera.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.ok = True
            get.return_value.content = b"\xff\xd8jpeg"
            response = self.client.get("/api/camera/preview/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")


class CollectionApiTests(TestCase):
    def test_adding_same_card_sums_quantity(self):
        card = Card.objects.create(bandai_id=31, card_number="BT1-031", name="Son Goku")
        client = APIClient()
        first = client.post("/api/collection/", {"card_id": card.id, "quantity": 2}, format="json")
        second = client.post("/api/collection/", {"card_id": card.id, "quantity": 1}, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["quantity"], 3)


class ImageCacheTests(TestCase):
    def test_local_path_mirrors_cdn(self):
        from cards.images import local_path

        with override_settings(CARD_IMAGES_DIR="/cache"):
            path = local_path("https://files.bandai-tcg-plus.com/card_image/DB-EN/BT1/BT1-001_b.png")
        self.assertEqual(str(path), "/cache/DB-EN/BT1/BT1-001_b.png")

    def test_get_image_prefers_cache(self):
        from cards.images import get_image

        with tempfile.TemporaryDirectory() as tmp, override_settings(CARD_IMAGES_DIR=tmp):
            url = "https://files.bandai-tcg-plus.com/card_image/DB-EN/BT1/BT1-001.png"
            with mock.patch("cards.images._session") as session:
                session.return_value.get.return_value.content = b"png"
                self.assertEqual(get_image(url), b"png")
                self.assertEqual(get_image(url), b"png")
            self.assertEqual(session.return_value.get.call_count, 1)


class FacetsTests(TestCase):
    def test_facets_have_no_duplicates(self):
        for i, color in enumerate(["Red", "Blue", "Red"]):
            Card.objects.create(bandai_id=i + 1, card_number=f"BT1-{i:03d}", name="X", color=color)
        facets = APIClient().get("/api/cards/facets/").data
        self.assertEqual(facets["color"], ["Blue", "Red"])


class KeepWarmTests(TestCase):
    @override_settings(CAMERA_URL="")
    def test_keep_warm_runs_without_camera(self):
        from scans.tasks import keep_warm

        keep_warm()  # no debe fallar aunque no haya cámara ni catálogo

    def test_keep_warm_is_scheduled(self):
        from django.conf import settings

        entry = settings.CELERY_BEAT_SCHEDULE["keep-worker-warm"]
        self.assertEqual(entry["task"], "scans.tasks.keep_warm")



class BurstFixture:
    """Catálogo sintético, una sesión y ayudantes para los tests de modo ráfaga."""

    def setUp(self):
        from collection.models import CollectionEntry

        self.Entry = CollectionEntry
        self.client = APIClient()
        self.cards = []
        for seed in range(10):
            card = Card.objects.create(
                bandai_id=seed + 1, card_number=f"BT1-{seed:03d}", name=f"Carta {seed}"
            )
            prints = fp.compute(make_card(seed))
            CardFingerprint.objects.create(
                card=card,
                source_url=f"https://example.com/{seed}.png",
                phash=prints.phash,
                dhash=prints.dhash,
                orb=prints.orb,
                orb_count=prints.orb_count,
            )
            self.cards.append(card)
        self.session = self.client.post("/api/sessions/", {}, format="json").data["id"]

    def _scan(self, image_bytes, after_empty=True):
        upload = SimpleUploadedFile("frame.jpg", image_bytes, content_type="image/jpeg")
        data = {"image": upload, "session": self.session, "after_empty": "true" if after_empty else "false"}
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/scans/", data, format="multipart")
        self.assertEqual(response.status_code, 202)
        return self.client.get(f"/api/scans/{response.data['id']}/").data

    def _card_photo(self, seed):
        return encode_jpeg(make_photo(make_card(seed)))

    def _quantity(self, card):
        entry = self.Entry.objects.filter(card=card).first()
        return entry.quantity if entry else 0

    def _stats(self):
        return self.client.get(f"/api/sessions/{self.session}/").data["stats"]



@override_settings(MEDIA_ROOT=MEDIA, CELERY_TASK_ALWAYS_EAGER=True, AUTO_ADD_MIN_CONFIDENCE=0.72)
class BurstModeTests(BurstFixture, TestCase):
    """Modo ráfaga: auto-añadido a la colección por encima del umbral."""

    def test_confident_scan_is_added_and_repeats_sum(self):
        first = self._scan(self._card_photo(4))
        self.assertTrue(first["added_to_collection"])
        self.assertGreaterEqual(first["confidence"], 0.72)
        self.assertEqual(self._quantity(self.cards[4]), 1)
        self._scan(self._card_photo(4))  # segunda copia
        self.assertEqual(self._quantity(self.cards[4]), 2)
        self.assertEqual(self._stats()["added"], 2)

    def test_uncatalogued_goes_to_review_and_confirm_adds_it(self):
        scan = self._scan(self._card_photo(99))
        self.assertFalse(scan["added_to_collection"])
        self.assertEqual(self._stats()["review"], 1)

        target = self.cards[3]
        confirmed = self.client.post(
            f"/api/scans/{scan['id']}/confirm/", {"card_id": target.id}, format="json"
        ).data
        self.assertTrue(confirmed["added_to_collection"])
        self.assertEqual(self._quantity(target), 1)
        self.assertEqual(self._stats()["review"], 0)

    def test_undo_removes_the_copy(self):
        self._scan(self._card_photo(4))
        second = self._scan(self._card_photo(4))
        response = self.client.post(f"/api/scans/{second['id']}/undo/", {}, format="json")
        self.assertTrue(response.data["dismissed"])
        self.assertFalse(response.data["added_to_collection"])
        self.assertEqual(self._quantity(self.cards[4]), 1)
        first_id = self.client.get(f"/api/sessions/{self.session}/").data["scans"][-1]["id"]
        self.client.post(f"/api/scans/{first_id}/undo/", {}, format="json")
        self.assertEqual(self._quantity(self.cards[4]), 0)  # la entrada se borra

    def test_correcting_an_added_scan_moves_the_copy(self):
        scan = self._scan(self._card_photo(4))
        self.client.post(f"/api/scans/{scan['id']}/confirm/", {"card_id": self.cards[6].id}, format="json")
        self.assertEqual(self._quantity(self.cards[4]), 0)
        self.assertEqual(self._quantity(self.cards[6]), 1)

    def test_empty_frame_is_dismissed_silently(self):
        import numpy as np

        empty = np.full((720, 1280, 3), 35, np.uint8)
        scan = self._scan(encode_jpeg(empty))
        self.assertTrue(scan["dismissed"])
        self.assertFalse(scan["added_to_collection"])
        session = self.client.get(f"/api/sessions/{self.session}/").data
        self.assertEqual(session["stats"]["total"], 0)
        self.assertEqual(session["scans"], [])

    @override_settings(AUTO_ADD_MIN_CONFIDENCE=1.01)
    def test_threshold_is_respected(self):
        scan = self._scan(self._card_photo(4))
        self.assertFalse(scan["added_to_collection"])
        self.assertEqual(self._quantity(self.cards[4]), 0)

    def test_scans_outside_a_session_are_never_added(self):
        upload = SimpleUploadedFile("f.jpg", self._card_photo(4), content_type="image/jpeg")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post("/api/scans/", {"image": upload}, format="multipart")
        self.assertEqual(self._quantity(self.cards[4]), 0)



@override_settings(MEDIA_ROOT=MEDIA, CELERY_TASK_ALWAYS_EAGER=True, AUTO_ADD_MIN_CONFIDENCE=0.65)
class RepeatGuardTests(BurstFixture, TestCase):
    """Misma carta dos veces seguidas sin vaciar la zona → "¿Otra copia?"."""

    def test_recolocated_card_is_not_added(self):
        self._scan(self._card_photo(4))
        repeat = self._scan(self._card_photo(4), after_empty=False)
        self.assertTrue(repeat["repeat_suspect"])
        self.assertFalse(repeat["added_to_collection"])
        self.assertEqual(self._quantity(self.cards[4]), 1)
        self.assertEqual(self._stats()["review"], 1)

    def test_confirming_the_repeat_adds_another_copy(self):
        self._scan(self._card_photo(4))
        repeat = self._scan(self._card_photo(4), after_empty=False)
        data = self.client.post(
            f"/api/scans/{repeat['id']}/confirm/", {"card_id": self.cards[4].id}, format="json"
        ).data
        self.assertTrue(data["added_to_collection"])
        self.assertFalse(data["repeat_suspect"])
        self.assertEqual(self._quantity(self.cards[4]), 2)

    def test_two_copies_with_empty_zone_between_are_added(self):
        self._scan(self._card_photo(4))
        self._scan(self._card_photo(4), after_empty=True)
        self.assertEqual(self._quantity(self.cards[4]), 2)

    def test_swapping_for_a_different_card_is_added(self):
        self._scan(self._card_photo(4))
        other = self._scan(self._card_photo(6), after_empty=False)
        self.assertTrue(other["added_to_collection"])
        self.assertFalse(other["repeat_suspect"])

    def test_previous_undone_does_not_block(self):
        first = self._scan(self._card_photo(4))
        self.client.post(f"/api/scans/{first['id']}/undo/", {}, format="json")
        again = self._scan(self._card_photo(4), after_empty=False)
        self.assertTrue(again["added_to_collection"])



class CollectionExportTests(TestCase):
    def test_export_lists_every_entry_with_bandai_id(self):
        from collection.models import CollectionEntry

        a = Card.objects.create(bandai_id=4, card_number="BT1-001", name="Champa")
        b = Card.objects.create(bandai_id=1088, card_number="BT1-005", name="Champa PR")
        CollectionEntry.objects.create(card=a, quantity=2)
        CollectionEntry.objects.create(card=a, quantity=1, condition="played")
        CollectionEntry.objects.create(card=b, quantity=1)
        data = APIClient().get("/api/collection/export/").data
        self.assertEqual(len(data), 3)  # sin paginar
        self.assertEqual(
            data[0], {"bandai_id": 4, "card_number": "BT1-001", "name": "Champa", "quantity": 2, "condition": "near_mint"}
        )



@override_settings(ENHANCED_API_URL="http://enhanced:5173")
class CatalogSyncTests(TestCase):
    def _export(self, records, generated_at="2026-10-19T10:00:00+00:00"):
        response = mock.Mock()
        response.json.return_value = {"generated_at": generated_at, "count": len(records), "results": records}
        response.raise_for_status.return_value = None
        return response

    def test_first_sync_is_full_and_next_is_incremental(self):
        from cards.catalog_sync import run_sync
        from cards.models import CatalogSync

        with mock.patch("cards.catalog_sync.requests.get", return_value=self._export([BANDAI_LEADER])) as get, \
                mock.patch("cards.catalog_sync.build_pending", return_value=(2, 0)):
            first = run_sync()
        self.assertEqual(get.call_args.kwargs["params"], {})  # primera vez: completo
        self.assertEqual(get.call_args.args[0], "http://enhanced:5173/api/cards/export/")
        self.assertEqual((first.status, first.full, first.created, first.fingerprints), ("success", True, 1, 2))
        self.assertTrue(Card.objects.filter(bandai_id=4).exists())

        renamed = {**BANDAI_LEADER, "card_name": "Champa!"}
        with mock.patch("cards.catalog_sync.requests.get", return_value=self._export([renamed])) as get, \
                mock.patch("cards.catalog_sync.build_pending", return_value=(0, 0)):
            second = run_sync()
        self.assertEqual(get.call_args.kwargs["params"], {"updated_since": "2026-10-19T10:00:00+00:00"})
        self.assertEqual((second.full, second.created, second.updated), (False, 0, 1))
        self.assertEqual(Card.objects.get(bandai_id=4).name, "Champa!")
        self.assertEqual(CatalogSync.objects.count(), 2)

    def test_failure_is_recorded_and_does_not_move_the_cursor(self):
        import requests

        from cards.catalog_sync import run_sync

        with mock.patch("cards.catalog_sync.requests.get", side_effect=requests.ConnectionError("caído")):
            sync = run_sync()
        self.assertEqual(sync.status, "failed")
        self.assertIn("caído", sync.error)
        self.assertIsNone(sync.cursor)

    @override_settings(ENHANCED_API_URL="")
    def test_not_configured(self):
        from cards.catalog_sync import run_sync

        self.assertIn("ENHANCED_API_URL", run_sync().error)
