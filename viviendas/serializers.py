from rest_framework import serializers

from .models import Edificio, Terreno, Vivienda


class TerrenoSerializer(serializers.ModelSerializer):
    administrador_nombre = serializers.StringRelatedField(source="administrador")

    class Meta:
        model = Terreno
        fields = ("id", "codigo", "nombre", "direccion", "administrador", "administrador_nombre", "activo")


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

    def get_personas(self, obj):
        return [{"persona_id": a.persona_id, "nombre": str(a.persona), "rol": a.rol.nombre, "vigente": a.vigente()}
                for a in obj.autorizaciones.all()]

    def validate_codigo(self, value):
        return value.strip().upper()

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
