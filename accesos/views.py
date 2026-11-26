from django.db.models import Q
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from config.permisos import AlcanceMixin, AsignacionPolitica, PuntoAccesoPolitica
from config.protegido import BorradoProtegidoMixin

from .models import Autorizacion, PuntoAcceso
from .serializers import AsignacionSerializer, PuntoAccesoSerializer


class PuntoAccesoViewSet(AlcanceMixin, BorradoProtegidoMixin, ModelViewSet):
    """CRUD de puntos de acceso (requiere token JWT).

    Filtros: ?terreno=<id>, ?edificio=<id>, ?vivienda=<id>, ?tipo=peatonal|vehicular|puerta,
    ?ambito=terreno|edificio|vivienda, ?activo=true|false, ?buscar=texto (nombre).
    """

    serializer_class = PuntoAccesoSerializer
    politica = PuntoAccesoPolitica()

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
        return self.limitar_alcance(qs)

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


class AsignacionViewSet(AlcanceMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                        mixins.RetrieveModelMixin, GenericViewSet):
    """Operación del negocio: asignar una persona a una vivienda con su tipo de participación.

    POST /api/asignaciones/                 asigna (solo el propietario administrador de esa vivienda)
    GET  /api/asignaciones/                 lista las asignaciones que el solicitante puede ver
    GET  /api/asignaciones/{id}/            detalle
    POST /api/asignaciones/{id}/revocar/    termina la asignación (queda en el historial, activa = false)

    Filtros: ?vivienda=<id>, ?persona=<id>, ?rol=<nombre>, ?activa=true|false.
    No hay PUT, PATCH ni DELETE: una asignación no se edita ni se borra, se revoca.
    """

    serializer_class = AsignacionSerializer
    politica = AsignacionPolitica()

    def get_queryset(self):
        qs = (Autorizacion.objects.filter(vivienda__isnull=False)
              .select_related("persona", "vivienda", "terreno", "rol", "otorgada_por")
              .prefetch_related("puntos").order_by("id"))
        p = self.request.query_params
        for campo in ("vivienda", "persona"):
            if p.get(campo, "").isdigit():
                qs = qs.filter(**{f"{campo}_id": int(p[campo])})
        if p.get("rol"):
            qs = qs.filter(rol__nombre=p["rol"])
        if p.get("activa") in ("true", "false"):
            qs = qs.filter(activa=(p["activa"] == "true"))
        return self.limitar_alcance(qs)

    @action(detail=True, methods=["post"])
    def revocar(self, request, pk=None):
        asignacion = self.get_object()
        if not asignacion.activa:
            return Response({"detail": "Esta asignación ya estaba revocada."}, status=status.HTTP_400_BAD_REQUEST)
        asignacion.activa = False
        asignacion.save(update_fields=["activa"])
        return Response(self.get_serializer(asignacion).data)
