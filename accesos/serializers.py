from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from config.permisos import (autorizaciones_vigentes, es_staff, persona_de, puede_otorgar_en)
from viviendas.models import Vivienda

from .models import Autorizacion, AutorizacionPunto, PuntoAcceso, Rol


def autorizaciones_vigentes_de(vivienda):
    """Autorizaciones vigentes de una vivienda (de cualquier persona)."""
    hoy = timezone.localdate()
    return (Autorizacion.objects.filter(vivienda=vivienda, activa=True, fecha_inicio__lte=hoy)
            .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)))


def puntos_del_solicitante(usuario, vivienda):
    """Puntos de acceso que el propietario administrador tiene en esa vivienda (no puede dar más que eso)."""
    persona = persona_de(usuario)
    if persona is None:
        return set()
    propias = autorizaciones_vigentes(persona).filter(vivienda=vivienda, rol__puede_otorgar=True)
    return set(AutorizacionPunto.objects.filter(autorizacion__in=propias).values_list("punto_acceso_id", flat=True))


class PuntoAccesoSerializer(serializers.ModelSerializer):
    terreno_nombre = serializers.CharField(source="terreno.nombre", read_only=True)
    edificio_nombre = serializers.CharField(source="edificio.nombre", read_only=True, default=None)
    vivienda_codigo = serializers.CharField(source="vivienda.codigo", read_only=True, default=None)
    ambito = serializers.SerializerMethodField(
        help_text="vivienda = puerta privada, edificio = hall de una torre, terreno = entrada compartida.")
    personas_autorizadas = serializers.SerializerMethodField(
        help_text="Personas con una autorización vigente que incluye este punto.")

    class Meta:
        model = PuntoAcceso
        fields = ("id", "nombre", "tipo", "terreno", "terreno_nombre", "edificio", "edificio_nombre",
                  "vivienda", "vivienda_codigo", "ambito", "latitud", "longitud", "activo",
                  "personas_autorizadas")

    def get_ambito(self, obj):
        return "vivienda" if obj.vivienda_id else "edificio" if obj.edificio_id else "terreno"

    def get_personas_autorizadas(self, obj):
        return [
            {"persona_id": pp.autorizacion.persona_id, "nombre": str(pp.autorizacion.persona),
             "rol": pp.autorizacion.rol.nombre}
            for pp in obj.puntos_permitidos.all() if pp.autorizacion.vigente()
        ]

    def validate_nombre(self, value):
        if not value.strip():
            raise serializers.ValidationError("No puede estar vacío.")
        return value.strip()

    def validate_latitud(self, value):
        if value is not None and not -90 <= value <= 90:
            raise serializers.ValidationError("La latitud debe estar entre -90 y 90.")
        return value

    def validate_longitud(self, value):
        if value is not None and not -180 <= value <= 180:
            raise serializers.ValidationError("La longitud debe estar entre -180 y 180.")
        return value

    def validate(self, attrs):
        # En PATCH se combinan los datos nuevos con los que ya tiene el punto
        def valor(campo):
            return attrs[campo] if campo in attrs else getattr(self.instance, campo, None)

        nombre, terreno = valor("nombre"), valor("terreno")
        edificio, vivienda = valor("edificio"), valor("vivienda")
        lat, lon = valor("latitud"), valor("longitud")

        if edificio is not None and vivienda is not None:
            raise serializers.ValidationError(
                {"vivienda": "Un punto es del terreno, de un edificio o de una vivienda, nunca de ambos."})
        if terreno is not None and edificio is not None and edificio.terreno_id != terreno.id:
            raise serializers.ValidationError({"edificio": f"El edificio '{edificio.nombre}' no pertenece a {terreno.nombre}."})
        if terreno is not None and vivienda is not None and vivienda.terreno_id != terreno.id:
            raise serializers.ValidationError({"vivienda": f"La vivienda '{vivienda.codigo}' no pertenece a {terreno.nombre}."})
        if (lat is None) != (lon is None):
            raise serializers.ValidationError({"longitud" if lon is None else "latitud":
                                               "Latitud y longitud se informan juntas."})

        # Dos puntos con el mismo nombre en un terreno confunden el historial
        if nombre and terreno is not None:
            repetido = PuntoAcceso.objects.filter(terreno=terreno, nombre__iexact=nombre)
            if self.instance:
                repetido = repetido.exclude(pk=self.instance.pk)
            if repetido.exists():
                raise serializers.ValidationError({"nombre": f"Ya existe un punto '{nombre}' en {terreno.nombre}."})

        # Un punto que ya está asignado a autorizaciones no se cambia de terreno ni de vivienda
        if self.instance and self.instance.puntos_permitidos.exists():
            if (terreno is not None and terreno.id != self.instance.terreno_id) or \
               (getattr(vivienda, "id", None) != self.instance.vivienda_id):
                raise serializers.ValidationError(
                    "El punto ya está asignado a autorizaciones: no se puede cambiar de terreno o vivienda. "
                    "Desactívalo y crea otro.")
        return attrs


class AsignacionSerializer(serializers.ModelSerializer):
    """Asignar una persona a una vivienda con su tipo de participación (rol).

    Reglas: el solicitante debe ser el propietario administrador de esa vivienda (o personal de SmartConnect),
    la persona no puede estar ya asignada y los puntos de acceso deben ser coherentes con la vivienda.
    """

    persona_nombre = serializers.StringRelatedField(source="persona", read_only=True)
    vivienda = serializers.PrimaryKeyRelatedField(queryset=Vivienda.objects.all())
    vivienda_codigo = serializers.CharField(source="vivienda.codigo", read_only=True)
    terreno_nombre = serializers.CharField(source="terreno.nombre", read_only=True)
    rol = serializers.SlugRelatedField(
        slug_field="nombre", queryset=Rol.objects.all(),
        help_text="propietario_admin, propietario, arrendatario o residente.")
    otorgada_por_nombre = serializers.StringRelatedField(source="otorgada_por", read_only=True)
    puntos_acceso = serializers.PrimaryKeyRelatedField(
        source="puntos", many=True, queryset=PuntoAcceso.objects.all(), required=False,
        help_text="Puntos por los que podrá pasar. Si se omite, queda vinculada pero sin accesos.")
    vigente = serializers.SerializerMethodField()

    class Meta:
        model = Autorizacion
        fields = ("id", "persona", "persona_nombre", "vivienda", "vivienda_codigo", "terreno", "terreno_nombre",
                  "rol", "otorgada_por", "otorgada_por_nombre", "fecha_inicio", "fecha_fin", "activa",
                  "vigente", "puntos_acceso")
        read_only_fields = ("terreno", "otorgada_por", "activa")

    def get_vigente(self, obj):
        return obj.vigente()

    def validate(self, attrs):
        usuario = self.context["request"].user
        persona, vivienda, rol = attrs["persona"], attrs["vivienda"], attrs["rol"]

        # 1) Autoridad del solicitante (se comprueba primero: sin autoridad no se revela nada más)
        if not (es_staff(usuario) or puede_otorgar_en(usuario, vivienda)):
            raise PermissionDenied("Solo el propietario administrador de esta vivienda puede asignar personas.")

        # 2) Tipo de participación
        if rol.ambito != Rol.Ambito.VIVIENDA:
            raise serializers.ValidationError({"rol": f"El rol '{rol}' es del terreno: no se asigna a una vivienda."})
        if not persona.activo:
            raise serializers.ValidationError({"persona": "La persona está desactivada."})
        if not vivienda.activa:
            raise serializers.ValidationError({"vivienda": "La vivienda está desactivada."})

        # 3) Sin asignaciones duplicadas
        vigentes = autorizaciones_vigentes(persona).filter(vivienda=vivienda).select_related("rol")
        existente = vigentes.first()
        if existente:
            raise serializers.ValidationError(
                {"persona": f"{persona} ya está asignada a {vivienda.codigo} como {existente.rol}."})
        if rol.puede_otorgar and autorizaciones_vigentes_de(vivienda).filter(rol__puede_otorgar=True).exists():
            raise serializers.ValidationError({"rol": "La vivienda ya tiene un propietario administrador."})

        # 4) Fechas
        hoy = timezone.localdate()
        inicio, fin = attrs.get("fecha_inicio", hoy), attrs.get("fecha_fin")
        if fin is not None and fin < inicio:
            raise serializers.ValidationError({"fecha_fin": "No puede ser anterior a la fecha de inicio."})
        if fin is not None and fin < hoy:
            raise serializers.ValidationError({"fecha_fin": "Esa fecha ya pasó: la asignación nacería vencida."})

        # 5) Puntos de acceso
        puntos = attrs.get("puntos", [])
        permitidos = None if es_staff(usuario) else puntos_del_solicitante(usuario, vivienda)
        for punto in puntos:
            if punto.terreno_id != vivienda.terreno_id:
                raise serializers.ValidationError({"puntos_acceso": f"'{punto.nombre}' no es del terreno de la vivienda."})
            if punto.vivienda_id and punto.vivienda_id != vivienda.pk:
                raise serializers.ValidationError({"puntos_acceso": f"'{punto.nombre}' es la puerta de otra vivienda."})
            if not punto.activo:
                raise serializers.ValidationError({"puntos_acceso": f"'{punto.nombre}' está desactivado."})
            if permitidos is not None and punto.pk not in permitidos:
                raise serializers.ValidationError(
                    {"puntos_acceso": f"No puedes dar acceso por '{punto.nombre}': tú no tienes ese acceso."})
        return attrs

    def create(self, validated_data):
        puntos = validated_data.pop("puntos", [])
        otorgante = persona_de(self.context["request"].user)
        try:
            with transaction.atomic():
                aut = Autorizacion(terreno=validated_data["vivienda"].terreno, otorgada_por=otorgante,
                                   **validated_data)
                aut.full_clean()
                aut.save()
                for punto in puntos:
                    ap = AutorizacionPunto(autorizacion=aut, punto_acceso=punto)
                    ap.full_clean()
                    ap.save()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict if hasattr(e, "error_dict") else e.messages)
        return aut
