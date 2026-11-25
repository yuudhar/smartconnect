from django.db.models import Q
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from config.protegido import BorradoProtegidoMixin

from .models import Edificio, Terreno, Vivienda
from .serializers import EdificioSerializer, TerrenoSerializer, ViviendaSerializer


class ViviendaViewSet(BorradoProtegidoMixin, ModelViewSet):
    """CRUD de viviendas. Filtros: ?terreno=<id>, ?edificio=<id>, ?tipo=casa|departamento, ?activa=true|false."""

    serializer_class = ViviendaSerializer

    def get_queryset(self):
        qs = Vivienda.objects.select_related("terreno", "edificio").prefetch_related(
            "autorizaciones__persona", "autorizaciones__rol").order_by("id")
        p = self.request.query_params
        for campo in ("terreno", "edificio"):
            if p.get(campo, "").isdigit():
                qs = qs.filter(**{f"{campo}_id": int(p[campo])})
        if p.get("tipo") in Vivienda.Tipo.values:
            qs = qs.filter(tipo=p["tipo"])
        if p.get("activa") in ("true", "false"):
            qs = qs.filter(activa=(p["activa"] == "true"))
        return qs


class TerrenoViewSet(BorradoProtegidoMixin, ModelViewSet):
    """CRUD de terrenos. Filtros: ?buscar=texto (código, nombre o dirección), ?administrador=<id>, ?activo=true|false."""

    serializer_class = TerrenoSerializer

    def get_queryset(self):
        qs = Terreno.objects.select_related("administrador").prefetch_related("edificios").order_by("id")
        p = self.request.query_params
        if p.get("buscar"):
            qs = qs.filter(Q(codigo__icontains=p["buscar"]) | Q(nombre__icontains=p["buscar"])
                           | Q(direccion__icontains=p["buscar"]))
        if p.get("administrador", "").isdigit():
            qs = qs.filter(administrador_id=int(p["administrador"]))
        if p.get("activo") in ("true", "false"):
            qs = qs.filter(activo=(p["activo"] == "true"))
        return qs


class EdificioViewSet(ReadOnlyModelViewSet):
    """Solo lectura: para consultar los id de edificio al crear departamentos."""

    queryset = Edificio.objects.order_by("id")
    serializer_class = EdificioSerializer
