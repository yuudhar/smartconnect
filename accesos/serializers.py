from rest_framework import serializers

from .models import PuntoAcceso


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
