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

    def test_changing_the_copies_of_an_added_scan(self):
        scan = self._scan(self._card_photo(4))
        url = f"/api/scans/{scan['id']}/copies/"
        self.assertEqual(self.client.post(url, {"copies": 3}, format="json").data["copies"], 3)
        self.assertEqual(self._quantity(self.cards[4]), 3)
        self.client.post(url, {"copies": 2}, format="json")
        self.assertEqual(self._quantity(self.cards[4]), 2)
        self.assertEqual(self.client.post(url, {"copies": 0}, format="json").status_code, 400)
        # Corregir la carta mueve todas sus copias; deshacer las quita todas.
        self.client.post(f"/api/scans/{scan['id']}/confirm/", {"card_id": self.cards[6].id}, format="json")
        self.assertEqual(self._quantity(self.cards[4]), 0)
        self.assertEqual(self._quantity(self.cards[6]), 2)
        self.client.post(f"/api/scans/{scan['id']}/undo/", {}, format="json")
        self.assertEqual(self._quantity(self.cards[6]), 0)
        self.assertEqual(self.client.post(url, {"copies": 2}, format="json").status_code, 400)

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

    def test_confirming_the_repeat_with_several_copies(self):
        self._scan(self._card_photo(4))
        repeat = self._scan(self._card_photo(4), after_empty=False)
        data = self.client.post(
            f"/api/scans/{repeat['id']}/confirm/", {"card_id": self.cards[4].id, "copies": 3}, format="json"
        ).data
        self.assertEqual(data["copies"], 3)
        self.assertEqual(self._quantity(self.cards[4]), 4)
        self.assertEqual(self._stats()["copies"], 4)
        self.client.post(f"/api/scans/{repeat['id']}/undo/", {}, format="json")
        self.assertEqual(self._quantity(self.cards[4]), 1)

    def test_previous_undone_does_not_block(self):
        first = self._scan(self._card_photo(4))
        self.client.post(f"/api/scans/{first['id']}/undo/", {}, format="json")
        again = self._scan(self._card_photo(4), after_empty=False)
        self.assertTrue(again["added_to_collection"])



@override_settings(MEDIA_ROOT=MEDIA, CELERY_TASK_ALWAYS_EAGER=True, AUTO_ADD_MIN_CONFIDENCE=0.65)
class BinderSessionTests(BurstFixture, TestCase):
    """Sesión de archivador: carta a carta por casillas, con la posición en la nota."""

    def setUp(self):
        super().setUp()
        from collection.models import Location

        self.binder = Location.objects.create(name="Archivador rojo", kind="binder")
        self.session = self.client.post(
            "/api/sessions/", {"mode": "binder", "location": self.binder.id}, format="json"
        ).data["id"]

    def _slot(self, seed, page, slot):
        upload = SimpleUploadedFile("frame.jpg", self._card_photo(seed), content_type="image/jpeg")
        data = {"image": upload, "session": self.session, "after_empty": "true", "binder_page": page, "binder_slot": slot}
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/scans/", data, format="multipart")
        self.assertEqual(response.status_code, 202, response.data)
        return self.client.get(f"/api/scans/{response.data['id']}/").data

    def entry(self, card):
        return self.Entry.objects.get(card=card, location=self.binder)

    def test_cards_go_to_the_binder_with_their_position(self):
        scan = self._slot(4, page=12, slot=6)
        self.assertTrue(scan["added_to_collection"])
        self.assertEqual((scan["binder_page"], scan["binder_slot"]), (12, 6))
        self.assertEqual(self.entry(self.cards[4]).notes, "Pág. 12 · fila 2 · col 3")
        session = self.client.get(f"/api/sessions/{self.session}/").data
        self.assertEqual(session["mode"], "binder")

    def test_same_card_side_by_side_is_two_copies(self):
        # En un archivador es normal tener copias juntas: no hay "¿Otra copia?".
        self._slot(4, page=1, slot=1)
        second = self._slot(4, page=1, slot=2)
        self.assertFalse(second["repeat_suspect"])
        entry = self.entry(self.cards[4])
        self.assertEqual(entry.quantity, 2)
        self.assertEqual(entry.notes.splitlines(), ["Pág. 1 · fila 1 · col 1", "Pág. 1 · fila 1 · col 2"])
        self.client.post(f"/api/scans/{second['id']}/undo/", {}, format="json")
        self.assertEqual((self.entry(self.cards[4]).quantity, self.entry(self.cards[4]).notes), (1, "Pág. 1 · fila 1 · col 1"))

    def test_recapturing_a_slot_replaces_the_previous_card(self):
        first = self._slot(4, page=3, slot=5)
        self._slot(6, page=3, slot=5)
        self.assertTrue(self.client.get(f"/api/scans/{first['id']}/").data["dismissed"])
        self.assertFalse(self.Entry.objects.filter(card=self.cards[4]).exists())
        self.assertEqual(self.entry(self.cards[6]).notes, "Pág. 3 · fila 2 · col 2")

    def test_slot_validation(self):
        upload = SimpleUploadedFile("frame.jpg", self._card_photo(4), content_type="image/jpeg")
        data = {"image": upload, "session": self.session, "binder_page": 1, "binder_slot": 10}
        self.assertEqual(self.client.post("/api/scans/", data, format="multipart").status_code, 400)


class CollectionExportTests(TestCase):
    def test_export_lists_every_entry_with_bandai_id_and_location(self):
        from collection.models import CollectionEntry, Location

        a = Card.objects.create(bandai_id=4, card_number="BT1-001", name="Champa")
        b = Card.objects.create(bandai_id=1088, card_number="BT1-005", name="Champa PR")
        deck = Location.objects.create(name="Mazo rojo", kind="deck")
        CollectionEntry.objects.create(card=a, location=Location.default(), quantity=2)
        CollectionEntry.objects.create(card=a, location=deck, quantity=1, notes="titular")
        CollectionEntry.objects.create(card=b, location=deck, quantity=1)
        data = APIClient().get("/api/collection/export/").data
        self.assertEqual(len(data), 3)  # sin paginar
        self.assertEqual(
            data[0],
            {
                "bandai_id": 4, "card_number": "BT1-001", "name": "Champa", "quantity": 2,
                "location_id": Location.default().id, "location": "Sin ubicar", "location_kind": "other", "notes": "",
            },
        )
        self.assertEqual((data[1]["location"], data[1]["notes"]), ("Mazo rojo", "titular"))


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



class CollectionAdjustTests(TestCase):
    def setUp(self):
        from collection.models import CollectionEntry, Location

        self.Entry, self.Location = CollectionEntry, Location
        self.card = Card.objects.create(bandai_id=4, card_number="BT1-001", name="Champa")
        self.deck = Location.objects.create(name="Mazo rojo", kind="deck")
        self.binder = Location.objects.create(name="Archivador", kind="binder")
        self.client = APIClient()

    def adjust(self, **body):
        return self.client.post("/api/collection/adjust/", {"bandai_id": 4, **body}, format="json")

    def put(self, location, quantity):
        self.Entry.objects.create(card=self.card, location=location, quantity=quantity)

    def by_location(self, data):
        return {loc["name"]: loc["quantity"] for loc in data["locations"]}

    def test_add_goes_to_unplaced_by_default(self):
        self.assertEqual(self.adjust(delta=1).data["quantity"], 1)
        data = self.adjust(delta=2).data
        self.assertEqual((data["quantity"], self.by_location(data)), (3, {"Sin ubicar": 3}))

    def test_add_to_a_location(self):
        data = self.adjust(delta=2, location=self.deck.id).data
        self.assertEqual(self.by_location(data), {"Mazo rojo": 2})

    def test_remove_takes_unplaced_first_then_the_only_other_location(self):
        self.put(self.Location.default(), 1)
        self.put(self.deck, 3)
        data = self.adjust(delta=-2).data
        self.assertEqual(self.by_location(data), {"Mazo rojo": 2})

    def test_remove_with_copies_in_several_locations_asks_which(self):
        self.put(self.deck, 2)
        self.put(self.binder, 1)
        response = self.adjust(delta=-1)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.by_location(response.data), {"Mazo rojo": 2, "Archivador": 1})
        data = self.adjust(delta=-1, location=self.binder.id).data
        self.assertEqual(self.by_location(data), {"Mazo rojo": 2})

    def test_last_copy_removes_the_entry(self):
        self.adjust(delta=1)
        data = self.adjust(delta=-1).data
        self.assertEqual((data["quantity"], data["locations"]), (0, []))
        self.assertFalse(self.Entry.objects.exists())

    def test_remove_from_empty_is_harmless(self):
        self.assertEqual(self.adjust(delta=-1).data["quantity"], 0)

    def test_validation(self):
        self.assertEqual(self.adjust(delta=0).status_code, 400)
        response = self.client.post("/api/collection/adjust/", {"bandai_id": 999, "delta": 1}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_move_keeps_the_total(self):
        self.put(self.Location.default(), 6)
        move = lambda **b: self.client.post(  # noqa: E731
            "/api/collection/move/", {"bandai_id": 4, **b}, format="json"
        )
        move(source=self.Location.default().id, target=self.deck.id, quantity=4)
        data = move(source=self.Location.default().id, target=self.binder.id, quantity=1).data
        self.assertEqual(data["quantity"], 6)
        self.assertEqual(self.by_location(data), {"Sin ubicar": 1, "Mazo rojo": 4, "Archivador": 1})
        too_many = move(source=self.binder.id, target=self.deck.id, quantity=2)
        self.assertEqual(too_many.status_code, 400)

    def test_note_per_location(self):
        self.put(self.binder, 1)
        data = self.client.post(
            "/api/collection/note/", {"bandai_id": 4, "location": self.binder.id, "notes": "página 12"}, format="json"
        ).data
        self.assertEqual(data["locations"][0]["notes"], "página 12")


class LocationTests(TestCase):
    def setUp(self):
        from collection.models import CollectionEntry, Location

        self.Entry, self.Location = CollectionEntry, Location
        self.client = APIClient()
        self.card = Card.objects.create(bandai_id=4, card_number="BT1-001", name="Champa")

    def test_list_always_includes_unplaced_with_totals(self):
        deck = self.client.post("/api/locations/", {"name": "Mazo rojo", "kind": "deck"}, format="json").data
        self.Entry.objects.create(card=self.card, location_id=deck["id"], quantity=4)
        data = self.client.get("/api/locations/").data
        self.assertEqual([(loc["name"], loc["copies"]) for loc in data], [("Sin ubicar", 0), ("Mazo rojo", 4)])
        self.assertTrue(data[0]["is_default"])

    def test_deleting_a_location_sends_its_copies_to_unplaced(self):
        deck = self.Location.objects.create(name="Mazo rojo")
        self.Entry.objects.create(card=self.card, location=self.Location.default(), quantity=2)
        self.Entry.objects.create(card=self.card, location=deck, quantity=4)
        self.assertEqual(self.client.delete(f"/api/locations/{deck.id}/").status_code, 204)
        self.assertEqual(list(self.Entry.objects.values_list("location__name", "quantity")), [("Sin ubicar", 6)])

    def test_unplaced_cannot_be_deleted(self):
        default = self.Location.default()
        self.assertEqual(self.client.delete(f"/api/locations/{default.id}/").status_code, 400)

    def test_burst_session_adds_into_its_location(self):
        from scans.models import Scan, ScanSession
        from scans.services import add_scan_to_collection

        deck = self.Location.objects.create(name="Mazo rojo")
        session = self.client.post("/api/sessions/", {"location": deck.id}, format="json").data
        self.assertEqual(session["location_name"], "Mazo rojo")
        scan = Scan.objects.create(session=ScanSession.objects.get(pk=session["id"]), matched_card=self.card, status="done")
        add_scan_to_collection(scan)
        self.assertEqual(list(self.Entry.objects.values_list("location__name", "quantity")), [("Mazo rojo", 1)])
