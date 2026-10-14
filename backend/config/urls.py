from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from cards.views import CardViewSet
from collection.views import CollectionEntryViewSet
from scans.views import ScanViewSet, camera_preview

router = DefaultRouter()
router.register("cards", CardViewSet, basename="card")
router.register("scans", ScanViewSet, basename="scan")
router.register("collection", CollectionEntryViewSet, basename="collection")


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/camera/preview/", camera_preview, name="camera-preview"),
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
