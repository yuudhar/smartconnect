from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from personas.models import Credencial, Persona
from viviendas.models import Edificio, Terreno, Vivienda


class Rol(models.Model):
    """Tipo de participación de una persona: en una vivienda o en el terreno."""

    class Ambito(models.TextChoices):
        VIVIENDA = "vivienda", "Vivienda"
        TERRENO = "terreno", "Terreno"

    nombre = models.CharField(max_length=30, unique=True)
    descripcion = models.CharField(max_length=120, blank=True)
    ambito = models.CharField(max_length=10, choices=Ambito.choices)
    puede_otorgar = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "roles"

    def __str__(self):
        return self.nombre


class PuntoAcceso(models.Model):
    """Entrada del terreno, acceso de un edificio o puerta de una vivienda."""

    class Tipo(models.TextChoices):
        PEATONAL = "peatonal", "Peatonal"
        VEHICULAR = "vehicular", "Vehicular"
        PUERTA = "puerta", "Puerta"

    nombre = models.CharField(max_length=80)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    terreno = models.ForeignKey(Terreno, on_delete=models.PROTECT, related_name="puntos_acceso")
    edificio = models.ForeignKey(
        Edificio, on_delete=models.PROTECT, null=True, blank=True, related_name="puntos_acceso"
    )
    vivienda = models.ForeignKey(
        Vivienda, on_delete=models.PROTECT, null=True, blank=True, related_name="puntos_acceso"
    )
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "punto de acceso"
        verbose_name_plural = "puntos de acceso"
        constraints = [
            # un punto es del terreno, de un edificio o de una vivienda, nunca de ambos
            models.CheckConstraint(
                condition=Q(edificio__isnull=True) | Q(vivienda__isnull=True),
                name="punto_edificio_o_vivienda_no_ambos",
            ),
        ]

    def clean(self):
        if self.edificio_id and self.edificio.terreno_id != self.terreno_id:
            raise ValidationError({"edificio": "El edificio debe ser del mismo terreno."})
        if self.vivienda_id and self.vivienda.terreno_id != self.terreno_id:
            raise ValidationError({"vivienda": "La vivienda debe ser del mismo terreno."})

    def __str__(self):
        return f"{self.nombre} ({self.terreno})"


class Autorizacion(models.Model):
    """Vínculo de una persona con un terreno y, si corresponde, con una vivienda, según su rol."""

    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="autorizaciones")
    terreno = models.ForeignKey(Terreno, on_delete=models.PROTECT, related_name="autorizaciones")
    vivienda = models.ForeignKey(
        Vivienda, on_delete=models.PROTECT, null=True, blank=True, related_name="autorizaciones",
        help_text="Vacío para roles de ámbito terreno (trabajador).",
    )
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name="autorizaciones")
    otorgada_por = models.ForeignKey(
        Persona, on_delete=models.SET_NULL, null=True, blank=True, related_name="autorizaciones_otorgadas"
    )
    fecha_inicio = models.DateField(default=date.today)
    fecha_fin = models.DateField(null=True, blank=True, help_text="Vacío = indefinida.")
    activa = models.BooleanField(default=True)
    puntos = models.ManyToManyField(PuntoAcceso, through="AutorizacionPunto", related_name="autorizaciones")

    class Meta:
        verbose_name_plural = "autorizaciones"
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=F("fecha_inicio")),
                name="autorizacion_fecha_fin_posterior",
            ),
        ]

    def clean(self):
        if not self.rol_id:
            return
        if self.rol.ambito == Rol.Ambito.VIVIENDA and not self.vivienda_id:
            raise ValidationError({"vivienda": f"El rol '{self.rol}' requiere una vivienda."})
        if self.rol.ambito == Rol.Ambito.TERRENO and self.vivienda_id:
            raise ValidationError({"vivienda": f"El rol '{self.rol}' es del terreno: no lleva vivienda."})
        if self.vivienda_id and self.vivienda.terreno_id != self.terreno_id:
            raise ValidationError({"vivienda": "La vivienda debe pertenecer al terreno indicado."})

    def vigente(self, hoy=None):
        hoy = hoy or timezone.localdate()
        return self.activa and self.fecha_inicio <= hoy and (self.fecha_fin is None or hoy <= self.fecha_fin)

    def __str__(self):
        lugar = self.vivienda or self.terreno
        return f"{self.persona} · {self.rol} · {lugar}"


class AutorizacionPunto(models.Model):
    """Puntos de acceso por los que puede pasar quien tiene la autorización (N:M)."""

    autorizacion = models.ForeignKey(Autorizacion, on_delete=models.CASCADE, related_name="puntos_permitidos")
    punto_acceso = models.ForeignKey(PuntoAcceso, on_delete=models.CASCADE, related_name="puntos_permitidos")

    class Meta:
        verbose_name = "punto permitido"
        verbose_name_plural = "puntos permitidos"
        constraints = [
            models.UniqueConstraint(fields=["autorizacion", "punto_acceso"], name="autorizacion_punto_unico"),
        ]

    def clean(self):
        if self.punto_acceso.terreno_id != self.autorizacion.terreno_id:
            raise ValidationError("El punto de acceso debe ser del mismo terreno de la autorización.")
        viv = self.autorizacion.vivienda
        if self.punto_acceso.vivienda_id and self.punto_acceso.vivienda_id != (viv.pk if viv else None):
            raise ValidationError("No se puede dar acceso a la puerta de otra vivienda.")

    def __str__(self):
        return f"{self.autorizacion.persona} → {self.punto_acceso.nombre}"


class RegistroAcceso(models.Model):
    """Historial de intentos: quién, por dónde, cuándo y con qué resultado."""

    class Sentido(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SALIDA = "salida", "Salida"

    class Medio(models.TextChoices):
        RFID = "rfid", "RFID"
        APP = "app", "App"

    class Resultado(models.TextChoices):
        PERMITIDO = "permitido", "Permitido"
        DENEGADO = "denegado", "Denegado"

    fecha_hora = models.DateTimeField(default=timezone.now, db_index=True)
    punto_acceso = models.ForeignKey(PuntoAcceso, on_delete=models.PROTECT, related_name="registros")
    sentido = models.CharField(max_length=10, choices=Sentido.choices, default=Sentido.ENTRADA)
    medio = models.CharField(max_length=10, choices=Medio.choices)
    persona = models.ForeignKey(Persona, on_delete=models.SET_NULL, null=True, blank=True, related_name="registros")
    credencial = models.ForeignKey(
        Credencial, on_delete=models.SET_NULL, null=True, blank=True, related_name="registros"
    )
    uid_recibido = models.CharField(max_length=32, null=True, blank=True, help_text="UID leído, aunque sea desconocido.")
    autorizacion = models.ForeignKey(
        Autorizacion, on_delete=models.SET_NULL, null=True, blank=True, related_name="registros",
        help_text="Autorización que justificó el paso.",
    )
    resultado = models.CharField(max_length=10, choices=Resultado.choices)
    motivo = models.CharField(max_length=120, null=True, blank=True)
    distancia_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Solo app (simulado).")

    class Meta:
        verbose_name = "registro de acceso"
        verbose_name_plural = "registros de acceso"
        ordering = ["-fecha_hora"]

    def __str__(self):
        quien = self.persona or self.uid_recibido or "desconocido"
        return f"{self.fecha_hora:%Y-%m-%d %H:%M} · {quien} · {self.punto_acceso.nombre} · {self.resultado}"


class AperturaDispositivo(models.Model):
    """Confirmación del dispositivo físico (prevista para la integración)."""

    class Estado(models.TextChoices):
        ABRIO = "abrio", "Abrió"
        NO_ABRIO = "no_abrio", "No abrió"
        SIN_RESPUESTA = "sin_respuesta", "Sin respuesta"

    registro = models.OneToOneField(RegistroAcceso, on_delete=models.CASCADE, related_name="apertura")
    fecha_hora = models.DateTimeField(default=timezone.now)
    estado = models.CharField(max_length=15, choices=Estado.choices)

    class Meta:
        verbose_name = "apertura de dispositivo"
        verbose_name_plural = "aperturas de dispositivo"

    def __str__(self):
        return f"{self.registro_id} · {self.estado}"
