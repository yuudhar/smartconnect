from django.contrib import admin

from .models import AperturaDispositivo, Autorizacion, AutorizacionPunto, PuntoAcceso, RegistroAcceso, Rol

admin.site.register([Rol, PuntoAcceso, Autorizacion, AutorizacionPunto, RegistroAcceso, AperturaDispositivo])
