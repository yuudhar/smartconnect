from rest_framework.routers import SimpleRouter

from .views import PersonaViewSet

router = SimpleRouter()
router.register("personas", PersonaViewSet, basename="persona")

urlpatterns = router.urls
