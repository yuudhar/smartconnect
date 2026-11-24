from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.response import Response


class BorradoProtegidoMixin:
    """Si el registro tiene datos relacionados protegidos, responde 409 en vez de un error 500."""

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError as e:
            relacionados = sorted({obj._meta.verbose_name_plural for obj in e.protected_objects})
            return Response(
                {
                    "detail": "No se puede eliminar: tiene datos relacionados. Desactívalo con PATCH (activo/activa = false).",
                    "relacionados": relacionados,
                },
                status=status.HTTP_409_CONFLICT,
            )
