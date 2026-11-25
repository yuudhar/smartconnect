from django.contrib import admin
from django.urls import include, path

from .views import inicio

urlpatterns = [
    path("", inicio),                          # página de inicio con las rutas disponibles
    path("admin/", admin.site.urls),
    path("api/", include("personas.urls")),   # CRUD Integrante 1
    path("api/", include("viviendas.urls")),  # CRUD Integrante 2
    path("api/", include("accesos.urls")),    # CRUD de puntos de acceso
]
