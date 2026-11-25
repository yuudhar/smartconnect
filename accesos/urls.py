from rest_framework.routers import SimpleRouter

from .views import PuntoAccesoViewSet

router = SimpleRouter()
router.register("puntos-acceso", PuntoAccesoViewSet, basename="punto-acceso")

urlpatterns = router.urls
