import re

from rest_framework import serializers

from .models import Persona


def dv_rut(numero: str) -> str:
    suma, factor = 0, 2
    for d in reversed(numero):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    dv = 11 - suma % 11
    return "0" if dv == 11 else "K" if dv == 10 else str(dv)


class PersonaSerializer(serializers.ModelSerializer):
    vinculos = serializers.SerializerMethodField(help_text="Viviendas o terrenos con los que se relaciona y su rol.")

    class Meta:
        model = Persona
        fields = ("id", "rut", "nombres", "apellidos", "email", "telefono", "activo", "creado_en", "vinculos")
        read_only_fields = ("creado_en",)

    def get_vinculos(self, obj):
        return [
            {
                "rol": a.rol.nombre,
                "terreno": a.terreno.nombre,
                "vivienda": a.vivienda.codigo if a.vivienda else None,
                "vigente": a.vigente(),
            }
            for a in obj.autorizaciones.all()
        ]

    def validate_rut(self, value):
        """Acepta 12345678-5 o 12.345.678-5 y lo guarda con puntos; valida el dígito verificador."""
        limpio = value.replace(".", "").replace(" ", "").upper()
        m = re.fullmatch(r"(\d{7,8})-([\dK])", limpio)
        if not m:
            raise serializers.ValidationError("Formato inválido. Usa 12345678-5 o 12.345.678-5.")
        numero, dv = m.groups()
        if dv_rut(numero) != dv:
            raise serializers.ValidationError("El dígito verificador no corresponde.")
        formateado = f"{int(numero):,}".replace(",", ".") + f"-{dv}"
        qs = Persona.objects.filter(rut=formateado)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe una persona con este RUT.")
        return formateado

    def validate_nombres(self, value):
        if not value.strip():
            raise serializers.ValidationError("No puede estar vacío.")
        return value.strip()

    def validate_apellidos(self, value):
        return self.validate_nombres(value)

    def validate_email(self, value):
        return value.lower()
