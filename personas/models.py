from datetime import date

from django.db import models


class Persona(models.Model):
    """Persona que participa en el sistema (datos ficticios)."""

    rut = models.CharField(max_length=12, unique=True, help_text="Ej. 12.345.678-5")
    nombres = models.CharField(max_length=80)
    apellidos = models.CharField(max_length=80)
    email = models.EmailField(max_length=254, unique=True)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return f"{self.nombres} {self.apellidos}"


class Credencial(models.Model):
    """Credencial RFID personal: un solo titular, no se comparte."""

    class Tipo(models.TextChoices):
        TARJETA = "tarjeta", "Tarjeta"
        LLAVERO = "llavero", "Llavero"

    class Estado(models.TextChoices):
        ACTIVA = "activa", "Activa"
        BLOQUEADA = "bloqueada", "Bloqueada"
        PERDIDA = "perdida", "Perdida"

    uid = models.CharField(max_length=32, unique=True)
    persona = models.ForeignKey(Persona, on_delete=models.PROTECT, related_name="credenciales")
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.TARJETA)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVA)
    fecha_emision = models.DateField(default=date.today)

    class Meta:
        verbose_name_plural = "credenciales"

    def __str__(self):
        return f"{self.uid} ({self.persona})"
