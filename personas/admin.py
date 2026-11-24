from django.contrib import admin

from .models import Credencial, Persona

admin.site.register([Persona, Credencial])
