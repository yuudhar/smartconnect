from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from config.protegido import BorradoProtegidoMixin

from .models import PuntoAcceso
from .serializers import PuntoAccesoSerializer


class PuntoAccesoViewSet(BorradoProtegidoMixin, ModelViewSet):
    """CRUD de puntos de acceso.

    Filtros: ?terreno=<id>, ?edificio=<id>, ?vivienda=<id>, ?tipo=peatonal|vehicular|puerta,
    ?ambito=terreno|edificio|vivienda, ?activo=true|false, ?buscar=texto (nombre).
    """

    serializer_class = PuntoAccesoSerializer

    def get_queryset(self):
        qs = PuntoAcceso.objects.select_related("terreno", "edificio", "vivienda").prefetch_related(
            "puntos_permitidos__autorizacion__persona", "puntos_permitidos__autorizacion__rol").order_by("id")
        p = self.request.query_params
        for campo in ("terreno", "edificio", "vivienda"):
            if p.get(campo, "").isdigit():
                qs = qs.filter(**{f"{campo}_id": int(p[campo])})
        if p.get("tipo") in PuntoAcceso.Tipo.values:
            qs = qs.filter(tipo=p["tipo"])
        if p.get("ambito") == "vivienda":
            qs = qs.filter(vivienda__isnull=False)
        elif p.get("ambito") == "edificio":
            qs = qs.filter(edificio__isnull=False)
        elif p.get("ambito") == "terreno":
            qs = qs.filter(edificio__isnull=True, vivienda__isnull=True)
        if p.get("activo") in ("true", "false"):
            qs = qs.filter(activo=(p["activo"] == "true"))
        if p.get("buscar"):
            qs = qs.filter(Q(nombre__icontains=p["buscar"]))
        return qs

    def destroy(self, request, *args, **kwargs):
        punto = self.get_object()
        asignado = punto.puntos_permitidos.count()
        if asignado:
            return Response(
                {"detail": "No se puede eliminar: está asignado a autorizaciones. Desactívalo con PATCH (activo = false).",
                 "relacionados": ["autorizaciones"]},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)  # si tiene historial, el mixin responde 409
