"""Permisos de SmartConnect: el JWT identifica a la cuenta y estas reglas deciden qué puede hacer.

Cada cuenta (User) se vincula con una Persona (Persona.usuario). Lo que la persona puede ver o cambiar
depende de su alcance:

    personal SmartConnect  cuenta con is_staff=True: ve y administra todo.
    administrador          persona que es Terreno.administrador: administra ese terreno, sus viviendas y
                           sus puntos de acceso.
    propietario_admin      rol con puede_otorgar en una vivienda: administra las personas de esa vivienda
                           (la operación de asignar está en accesos/asignaciones).
    otras personas         solo ven lo que las vincula: sus viviendas, sus terrenos, sus puntos permitidos.

Los listados se filtran a lo permitido. Si la persona consulta o cambia un registro concreto fuera de su
alcance, la API responde 403. Sin token válido responde 401.
"""
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated

# ---------------------------------------------------------------- identidad y alcance


def es_staff(user):
    return bool(user and user.is_authenticated and user.is_staff)


def persona_de(user):
    """Persona activa vinculada a la cuenta, o None (cuenta sin persona o persona desactivada)."""
    if not user or not user.is_authenticated:
        return None
    from personas.models import Persona
    return Persona.objects.filter(usuario=user, activo=True).first()


def autorizaciones_vigentes(persona):
    """Autorizaciones activas de la persona cuyas fechas incluyen hoy."""
    from accesos.models import Autorizacion
    hoy = timezone.localdate()
    return (Autorizacion.objects.filter(persona=persona, activa=True, fecha_inicio__lte=hoy)
            .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)))


def ids_terrenos_administrados(user):
    persona = persona_de(user)
    if not persona:
        return set()
    from viviendas.models import Terreno
    return set(Terreno.objects.filter(administrador=persona).values_list("pk", flat=True))


def ids_terrenos_vinculados(user):
    """Terrenos que administra o donde tiene una autorización vigente (vivienda o trabajo)."""
    persona = persona_de(user)
    if not persona:
        return set()
    vinculados = set(autorizaciones_vigentes(persona).values_list("terreno_id", flat=True))
    return ids_terrenos_administrados(user) | vinculados


def ids_viviendas_vinculadas(user):
    persona = persona_de(user)
    if not persona:
        return set()
    return set(autorizaciones_vigentes(persona).filter(vivienda__isnull=False)
               .values_list("vivienda_id", flat=True))


def ids_viviendas_que_administra(user):
    """Viviendas donde la persona es propietario administrador (rol con puede_otorgar) vigente."""
    persona = persona_de(user)
    if not persona:
        return set()
    return set(autorizaciones_vigentes(persona).filter(rol__puede_otorgar=True, vivienda__isnull=False)
               .values_list("vivienda_id", flat=True))


def puede_otorgar_en(user, vivienda):
    """El solicitante es propietario administrador vigente de esa vivienda."""
    return vivienda.pk in ids_viviendas_que_administra(user)


def puede_gestionar_personas(user):
    """Puede registrar personas: personal, administradores de terreno y propietarios administradores."""
    return es_staff(user) or bool(ids_terrenos_administrados(user)) or bool(ids_viviendas_que_administra(user))


# ---------------------------------------------------------------- políticas por recurso


class Politica:
    """Reglas de un recurso. Cada ViewSet usa una (atributo `politica`)."""

    def visibles(self, user, qs):
        raise NotImplementedError

    def puede_ver(self, user, obj):
        raise NotImplementedError

    def puede_modificar(self, user, obj):
        return False

    def puede_eliminar(self, user, obj):
        return False

    def puede_crear(self, user, datos=None):
        """datos=None es la comprobación previa (antes de validar); con datos es la definitiva."""
        return es_staff(user)

    def validar_cambio(self, user, obj, datos):
        """Se llama al actualizar, ya con los datos validados. Lanza PermissionDenied si no corresponde."""


class TerrenoPolitica(Politica):
    def visibles(self, user, qs):
        return qs if es_staff(user) else qs.filter(pk__in=ids_terrenos_vinculados(user))

    def puede_ver(self, user, obj):
        return es_staff(user) or obj.pk in ids_terrenos_vinculados(user)

    def puede_modificar(self, user, obj):
        return es_staff(user) or obj.pk in ids_terrenos_administrados(user)

    def puede_eliminar(self, user, obj):
        return es_staff(user)

    def validar_cambio(self, user, obj, datos):
        nuevo = datos.get("administrador")
        if nuevo is not None and nuevo.pk != obj.administrador_id and not es_staff(user):
            raise PermissionDenied("Solo el personal de SmartConnect puede cambiar el administrador de un terreno.")


class EdificioPolitica(Politica):
    """Solo lectura: se ven los edificios de los terrenos visibles."""

    def visibles(self, user, qs):
        return qs if es_staff(user) else qs.filter(terreno_id__in=ids_terrenos_vinculados(user))

    def puede_ver(self, user, obj):
        return es_staff(user) or obj.terreno_id in ids_terrenos_vinculados(user)


class _PoliticaDeTerreno(Politica):
    """Base para viviendas y puntos de acceso: los gestiona el administrador del terreno."""

    def puede_modificar(self, user, obj):
        return es_staff(user) or obj.terreno_id in ids_terrenos_administrados(user)

    puede_eliminar = puede_modificar

    def puede_crear(self, user, datos=None):
        if es_staff(user):
            return True
        if datos is None:
            return bool(ids_terrenos_administrados(user))
        return datos["terreno"].pk in ids_terrenos_administrados(user)

    def validar_cambio(self, user, obj, datos):
        nuevo = datos.get("terreno")
        if nuevo is not None and nuevo.pk != obj.terreno_id and not es_staff(user) \
                and nuevo.pk not in ids_terrenos_administrados(user):
            raise PermissionDenied("No administras el terreno al que quieres mover el registro.")


class ViviendaPolitica(_PoliticaDeTerreno):
    def visibles(self, user, qs):
        if es_staff(user):
            return qs
        return qs.filter(Q(terreno_id__in=ids_terrenos_administrados(user))
                         | Q(pk__in=ids_viviendas_vinculadas(user)))

    def puede_ver(self, user, obj):
        return (es_staff(user) or obj.terreno_id in ids_terrenos_administrados(user)
                or obj.pk in ids_viviendas_vinculadas(user))


class PuntoAccesoPolitica(_PoliticaDeTerreno):
    @staticmethod
    def _ids_permitidos(user):
        persona = persona_de(user)
        if not persona:
            return set()
        from accesos.models import AutorizacionPunto
        return set(AutorizacionPunto.objects.filter(autorizacion__in=autorizaciones_vigentes(persona))
                   .values_list("punto_acceso_id", flat=True))

    def visibles(self, user, qs):
        if es_staff(user):
            return qs
        return qs.filter(Q(terreno_id__in=ids_terrenos_administrados(user)) | Q(pk__in=self._ids_permitidos(user)))

    def puede_ver(self, user, obj):
        return (es_staff(user) or obj.terreno_id in ids_terrenos_administrados(user)
                or obj.pk in self._ids_permitidos(user))


class PersonaPolitica(Politica):
    @staticmethod
    def _ids_visibles(user):
        persona = persona_de(user)
        if not persona:
            return set()
        from personas.models import Persona
        gestionadas = Persona.objects.filter(
            Q(autorizaciones__terreno_id__in=ids_terrenos_administrados(user))
            | Q(autorizaciones__vivienda_id__in=ids_viviendas_que_administra(user))
        ).values_list("pk", flat=True)
        return {persona.pk} | set(gestionadas)

    def visibles(self, user, qs):
        return qs if es_staff(user) else qs.filter(pk__in=self._ids_visibles(user))

    def puede_ver(self, user, obj):
        return es_staff(user) or obj.pk in self._ids_visibles(user)

    def puede_modificar(self, user, obj):
        persona = persona_de(user)
        return es_staff(user) or (persona is not None and persona.pk == obj.pk)

    def puede_eliminar(self, user, obj):
        return es_staff(user)

    def puede_crear(self, user, datos=None):
        return puede_gestionar_personas(user)

    def validar_cambio(self, user, obj, datos):
        if es_staff(user):
            return
        for campo in ("rut", "activo"):
            if campo in datos and datos[campo] != getattr(obj, campo):
                raise PermissionDenied(f"Solo el personal de SmartConnect puede cambiar '{campo}'.")


# ---------------------------------------------------------------- piezas para los ViewSet


class PermisoDeAlcance(BasePermission):
    """Aplica la política del ViewSet: crear (comprobación previa) y acceso a un registro concreto."""

    message = "No tienes permiso para realizar esta acción sobre este recurso."

    def has_permission(self, request, view):
        if getattr(view, "action", None) == "create":
            return view.politica.puede_crear(request.user, None)
        return True

    def has_object_permission(self, request, view, obj):
        politica = view.politica
        if request.method in SAFE_METHODS:
            return politica.puede_ver(request.user, obj)
        if request.method == "DELETE":
            return politica.puede_eliminar(request.user, obj)
        return politica.puede_modificar(request.user, obj)


class AlcanceMixin:
    """JWT obligatorio + alcance por terreno/vivienda. Poner antes de ModelViewSet y definir `politica`.

    - Listados: solo los registros permitidos.
    - Detalle, PUT/PATCH y DELETE de un registro fuera de alcance: 403.
    - POST: 403 si la persona no puede crear en ese terreno.
    """

    politica = None
    permission_classes = [IsAuthenticated, PermisoDeAlcance]

    def limitar_alcance(self, qs):
        """Llamar al final de get_queryset. Solo el listado se filtra: el detalle responde 403, no 404."""
        return self.politica.visibles(self.request.user, qs) if self.action == "list" else qs

    def perform_create(self, serializer):
        if not self.politica.puede_crear(self.request.user, serializer.validated_data):
            raise PermissionDenied("No tienes permiso para crear en ese terreno.")
        serializer.save()

    def perform_update(self, serializer):
        self.politica.validar_cambio(self.request.user, serializer.instance, serializer.validated_data)
        serializer.save()
