from rest_framework import serializers

from .models import Edificio, Terreno, Vivienda


class TerrenoSerializer(serializers.ModelSerializer):
    administrador_nombre = serializers.StringRelatedField(source="administrador", read_only=True)
    edificios = serializers.SerializerMethodField(help_text="Nombres de los edificios del terreno.")
    total_viviendas = serializers.IntegerField(source="viviendas.count", read_only=True)
    total_puntos_acceso = serializers.IntegerField(source="puntos_acceso.count", read_only=True)

    class Meta:
        model = Terreno
        fields = ("id", "codigo", "nombre", "direccion", "administrador", "administrador_nombre",
                  "latitud", "longitud", "activo", "creado_en", "edificios", "total_viviendas",
                  "total_puntos_acceso")
        read_only_fields = ("creado_en",)
        # El código se valida a mano (sin distinguir mayúsculas), así que se quita el validador automático
        extra_kwargs = {"codigo": {"validators": []}}

    def get_edificios(self, obj):
        return [e.nombre for e in obj.edificios.all()]

    def validate_codigo(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("No puede estar vacío.")
        qs = Terreno.objects.filter(codigo=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un terreno con este código.")
        return value

    def validate_nombre(self, value):
        if not value.strip():
            raise serializers.ValidationError("No puede estar vacío.")
        return value.strip()

    def validate_administrador(self, value):
        if not value.activo:
            raise serializers.ValidationError("El administrador debe ser una persona activa.")
        return value

    def validate_latitud(self, value):
        if value is not None and not -90 <= value <= 90:
            raise serializers.ValidationError("La latitud debe estar entre -90 y 90.")
        return value

    def validate_longitud(self, value):
        if value is not None and not -180 <= value <= 180:
            raise serializers.ValidationError("La longitud debe estar entre -180 y 180.")
        return value

    def validate(self, attrs):
        # Latitud y longitud van juntas: se informan las dos o ninguna (también en PATCH)
        lat = attrs["latitud"] if "latitud" in attrs else getattr(self.instance, "latitud", None)
        lon = attrs["longitud"] if "longitud" in attrs else getattr(self.instance, "longitud", None)
        if (lat is None) != (lon is None):
            raise serializers.ValidationError({"longitud" if lon is None else "latitud":
                                               "Latitud y longitud se informan juntas."})
        return attrs


class EdificioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edificio
        fields = ("id", "terreno", "nombre", "pisos", "activo")


class ViviendaSerializer(serializers.ModelSerializer):
    terreno_nombre = serializers.CharField(source="terreno.nombre", read_only=True)
    edificio_nombre = serializers.CharField(source="edificio.nombre", read_only=True, default=None)
    personas = serializers.SerializerMethodField(help_text="Personas vinculadas a la vivienda y su rol.")

    class Meta:
        model = Vivienda
        fields = ("id", "codigo", "tipo", "numero", "terreno", "terreno_nombre",
                  "edificio", "edificio_nombre", "activa", "personas")
        extra_kwargs = {"codigo": {"validators": []}}  # se valida en validate_codigo

    def get_personas(self, obj):
        return [{"persona_id": a.persona_id, "nombre": str(a.persona), "rol": a.rol.nombre, "vigente": a.vigente()}
                for a in obj.autorizaciones.all()]

    def validate_codigo(self, value):
        value = value.strip().upper()
        # Se compara ya en mayúsculas: "lr-a-101" y "LR-A-101" son el mismo código
        qs = Vivienda.objects.filter(codigo=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe una vivienda con este código.")
        return value

    def validate(self, attrs):
        # En PATCH se combinan los datos nuevos con los que ya tiene la vivienda
        tipo = attrs.get("tipo", getattr(self.instance, "tipo", None))
        terreno = attrs.get("terreno", getattr(self.instance, "terreno", None))
        edificio = attrs["edificio"] if "edificio" in attrs else getattr(self.instance, "edificio", None)

        if tipo == Vivienda.Tipo.CASA and edificio is not None:
            raise serializers.ValidationError({"edificio": "Una casa va directo en el terreno: no lleva edificio."})
        if tipo == Vivienda.Tipo.DEPARTAMENTO and edificio is None:
            raise serializers.ValidationError({"edificio": "Un departamento debe indicar su edificio."})
        if edificio is not None and terreno is not None and edificio.terreno_id != terreno.id:
            raise serializers.ValidationError({"edificio": f"El edificio '{edificio.nombre}' no pertenece a {terreno.nombre}."})
        return attrs
