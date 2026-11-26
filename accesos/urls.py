from rest_framework.routers import SimpleRouter

from .views import AsignacionViewSet, PuntoAccesoViewSet

router = SimpleRouter()
router.register("puntos-acceso", PuntoAccesoViewSet, basename="punto-acceso")
router.register("asignaciones", AsignacionViewSet, basename="asignacion")

urlpatterns = router.urls
