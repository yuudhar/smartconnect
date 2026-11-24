from django.db.models import Q
from rest_framework.viewsets import ModelViewSet

from config.protegido import BorradoProtegidoMixin

from .models import Persona
from .serializers import PersonaSerializer


class PersonaViewSet(BorradoProtegidoMixin, ModelViewSet):
    """CRUD de personas. Filtros: ?buscar=texto (nombre, apellido, RUT o email) y ?activo=true|false."""

    serializer_class = PersonaSerializer

    def get_queryset(self):
        qs = Persona.objects.prefetch_related("autorizaciones__rol", "autorizaciones__terreno",
                                              "autorizaciones__vivienda").order_by("id")
        buscar = self.request.query_params.get("buscar")
        if buscar:
            qs = qs.filter(Q(nombres__icontains=buscar) | Q(apellidos__icontains=buscar)
                           | Q(rut__icontains=buscar) | Q(email__icontains=buscar))
        activo = self.request.query_params.get("activo")
        if activo in ("true", "false"):
            qs = qs.filter(activo=(activo == "true"))
        return qs
