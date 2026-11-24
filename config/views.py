from django.http import JsonResponse
from django.urls import URLResolver, get_resolver


def inicio(request):
    """Página de inicio: muestra las rutas de la API que están disponibles."""
    rutas = []
    for p in get_resolver().url_patterns:
        if isinstance(p, URLResolver) and str(p.pattern) == "api/":
            for sub in p.url_patterns:
                ruta = str(sub.pattern).lstrip("^").rstrip("$")
                if "format" not in ruta:
                    rutas.append("/api/" + ruta.replace("(?P<pk>[^/.]+)", "{id}"))
    return JsonResponse(
        {
            "api": "SmartConnect",
            "estado": "funcionando",
            "rutas": sorted(set(rutas)) or ["(todavía no hay CRUD: se agregan en las ramas feature/personas y feature/viviendas)"],
            "admin": "/admin/",
        },
        json_dumps_params={"ensure_ascii": False, "indent": 2},
    )
