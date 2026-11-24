from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from personas.models import Persona


class Terreno(models.Model):
    """Terreno cercado (conjunto residencial) con un administrador responsable."""

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=80)
    direccion = models.CharField(max_length=150)
    administrador = models.ForeignKey(
        Persona, on_delete=models.PROTECT, related_name="terrenos_administrados"
    )
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class Edificio(models.Model):
    """Edificio (torre o block) dentro de un terreno. Solo existe para departamentos."""

    terreno = models.ForeignKey(Terreno, on_delete=models.PROTECT, related_name="edificios")
    nombre = models.CharField(max_length=50)
    pisos = models.PositiveSmallIntegerField(default=1)
    activo = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["terreno", "nombre"], name="edificio_nombre_unico_por_terreno"),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.terreno})"


class Vivienda(models.Model):
    """Casa o departamento. Una casa va directo en el terreno; un depto dentro de un edificio."""

    class Tipo(models.TextChoices):
        CASA = "casa", "Casa"
        DEPARTAMENTO = "departamento", "Departamento"

    codigo = models.CharField(max_length=20, unique=True)
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    numero = models.CharField(max_length=20, help_text="Ej. 304 (depto) o 12 (casa)")
    terreno = models.ForeignKey(Terreno, on_delete=models.PROTECT, related_name="viviendas")
    edificio = models.ForeignKey(
        Edificio, on_delete=models.PROTECT, null=True, blank=True, related_name="viviendas"
    )
    activa = models.BooleanField(default=True)

    class Meta:
        constraints = [
            # casa -> sin edificio; departamento -> con edificio
            models.CheckConstraint(
                condition=(Q(tipo="casa", edificio__isnull=True) | Q(tipo="departamento", edificio__isnull=False)),
                name="vivienda_casa_sin_edificio_depto_con_edificio",
            ),
        ]

    def clean(self):
        if self.edificio_id and self.terreno_id and self.edificio.terreno_id != self.terreno_id:
            raise ValidationError({"edificio": "El edificio debe pertenecer al mismo terreno de la vivienda."})

    def __str__(self):
        return f"{self.codigo} · {self.get_tipo_display()} {self.numero}"
