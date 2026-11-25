from rest_framework.routers import SimpleRouter

from .views import EdificioViewSet, TerrenoViewSet, ViviendaViewSet

router = SimpleRouter()
router.register("viviendas", ViviendaViewSet, basename="vivienda")
# Apoyo (solo lectura) para elegir terreno y edificio al crear viviendas
router.register("terrenos", TerrenoViewSet, basename="terreno")
router.register("edificios", EdificioViewSet, basename="edificio")

urlpatterns = router.urls
