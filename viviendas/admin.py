from django.contrib import admin

from .models import Edificio, Terreno, Vivienda

admin.site.register([Terreno, Edificio, Vivienda])
