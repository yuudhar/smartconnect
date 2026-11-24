"""Carga datos ficticios para la Entrega 1 de SmartConnect.

Uso:
    python manage.py cargar_datos          # solo si la BD está vacía
    python manage.py cargar_datos --reset  # borra todo y vuelve a cargar
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction
from django.utils import timezone

from accesos.models import AperturaDispositivo, Autorizacion, AutorizacionPunto, PuntoAcceso, RegistroAcceso, Rol
from personas.models import Credencial, Persona
from viviendas.models import Edificio, Terreno, Vivienda


def rut_con_dv(numero: int) -> str:
    """Genera un RUT ficticio con dígito verificador válido (módulo 11)."""
    suma, factor = 0, 2
    for d in reversed(str(numero)):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    dv = 11 - suma % 11
    dv = "0" if dv == 11 else "K" if dv == 10 else str(dv)
    return f"{numero:,}".replace(",", ".") + f"-{dv}"


def crear(modelo, **campos):
    """Crea el objeto validando también las reglas de clean()."""
    obj = modelo(**campos)
    obj.full_clean()
    obj.save()
    return obj


class Command(BaseCommand):
    help = "Carga datos ficticios de SmartConnect (terrenos, viviendas, personas, accesos e historial)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Borra los datos existentes antes de cargar.")

    @transaction.atomic
    def handle(self, *args, **opts):
        modelos = (AperturaDispositivo, RegistroAcceso, AutorizacionPunto, Autorizacion, PuntoAcceso,
                   Rol, Vivienda, Edificio, Terreno, Credencial, Persona)
        if Persona.objects.exists() and not opts["reset"]:
            raise CommandError("La base ya tiene datos. Usa --reset para borrar y volver a cargar.")
        if opts["reset"]:
            # Vacía las tablas y reinicia los contadores de id, para que los id sean siempre los mismos
            tablas = [m._meta.db_table for m in modelos]
            for sql in connection.ops.sql_flush(no_style(), tablas, reset_sequences=True, allow_cascade=True):
                with connection.cursor() as cur:
                    cur.execute(sql)

        # ---------- Personas ----------
        datos_personas = [
            ("carlos", 11222333, "Carlos", "Muñoz Herrera", "+56 9 1111 1111"),   # administra los 2 terrenos
            ("ana", 12345678, "Ana", "Rojas Pinto", "+56 9 2222 2222"),           # propietaria admin A-101 y A-102
            ("benja", 19876543, "Benjamín", "Soto Lagos", "+56 9 3333 3333"),     # arrendatario A-101 y dueño Casa 3
            ("sofi", 17654321, "Sofía", "Díaz Morales", "+56 9 4444 4444"),       # trabajadora de Los Robles
            ("pedro", 10987654, "Pedro", "Fuentes Vidal", "+56 9 5555 5555"),     # propietario admin Casa 7
            ("ema", 21345678, "Ema", "Fuentes Araya", None),                      # residente Casa 7 (hija)
            ("vale", 16543210, "Valentina", "Pérez Castro", "+56 9 6666 6666"),   # propietaria admin B-201
            ("lucas", 20123456, "Lucas", "Vera Ortiz", "+56 9 7777 7777"),        # arrendatario vencido B-201
        ]
        p = {}
        for clave, num, nombres, apellidos, tel in datos_personas:
            p[clave] = crear(Persona, rut=rut_con_dv(num), nombres=nombres, apellidos=apellidos,
                             email=f"{clave}@smartconnect.test", telefono=tel)

        # ---------- Terrenos, edificios y viviendas ----------
        robles = crear(Terreno, codigo="TR-ROBLES", nombre="Condominio Los Robles",
                       direccion="Av. Los Robles 1500, Ñuñoa", administrador=p["carlos"],
                       latitud=Decimal("-33.456900"), longitud=Decimal("-70.597800"))
        bosque = crear(Terreno, codigo="TR-BOSQUE", nombre="Condominio El Bosque",
                       direccion="Camino El Bosque 320, Peñalolén", administrador=p["carlos"],
                       latitud=Decimal("-33.489100"), longitud=Decimal("-70.548300"))

        torre_a = crear(Edificio, terreno=robles, nombre="Torre A", pisos=8)
        torre_b = crear(Edificio, terreno=robles, nombre="Torre B", pisos=8)

        v = {
            "A-101": crear(Vivienda, codigo="LR-A-101", tipo="departamento", numero="101", terreno=robles, edificio=torre_a),
            "A-102": crear(Vivienda, codigo="LR-A-102", tipo="departamento", numero="102", terreno=robles, edificio=torre_a),
            "B-201": crear(Vivienda, codigo="LR-B-201", tipo="departamento", numero="201", terreno=robles, edificio=torre_b),
            "Casa 7": crear(Vivienda, codigo="EB-C-07", tipo="casa", numero="7", terreno=bosque),
            "Casa 3": crear(Vivienda, codigo="EB-C-03", tipo="casa", numero="3", terreno=bosque),
        }

        # ---------- Puntos de acceso ----------
        pa = {
            # Los Robles: entradas del terreno
            "peatonal_norte": crear(PuntoAcceso, nombre="Peatonal Norte", tipo="peatonal", terreno=robles,
                                    latitud=Decimal("-33.456700"), longitud=Decimal("-70.597900")),
            "reja_vehicular": crear(PuntoAcceso, nombre="Reja Vehicular", tipo="vehicular", terreno=robles),
            "porton_sur": crear(PuntoAcceso, nombre="Portón Sur", tipo="vehicular", terreno=robles),
            # Los Robles: accesos de edificios
            "hall_a": crear(PuntoAcceso, nombre="Hall Torre A", tipo="puerta", terreno=robles, edificio=torre_a),
            "hall_b": crear(PuntoAcceso, nombre="Hall Torre B", tipo="puerta", terreno=robles, edificio=torre_b),
            # Los Robles: puertas de viviendas
            "puerta_a101": crear(PuntoAcceso, nombre="Puerta A-101", tipo="puerta", terreno=robles, vivienda=v["A-101"]),
            "puerta_a102": crear(PuntoAcceso, nombre="Puerta A-102", tipo="puerta", terreno=robles, vivienda=v["A-102"]),
            # El Bosque
            "porton_bosque": crear(PuntoAcceso, nombre="Portón Principal", tipo="vehicular", terreno=bosque),
            "peatonal_bosque": crear(PuntoAcceso, nombre="Peatonal El Bosque", tipo="peatonal", terreno=bosque),
            "puerta_casa7": crear(PuntoAcceso, nombre="Puerta Casa 7", tipo="puerta", terreno=bosque, vivienda=v["Casa 7"]),
        }

        # ---------- Roles ----------
        r = {}
        for nombre, desc, ambito, otorga in [
            ("propietario_admin", "Dueño que administra las personas de su vivienda", "vivienda", True),
            ("propietario", "Copropietario de la vivienda", "vivienda", False),
            ("arrendatario", "Arrienda la vivienda", "vivienda", False),
            ("residente", "Convive en la vivienda sin ser dueño ni arrendatario", "vivienda", False),
            ("trabajador", "Trabaja en el terreno (conserje, guardia, jardinero)", "terreno", False),
        ]:
            r[nombre] = crear(Rol, nombre=nombre, descripcion=desc, ambito=ambito, puede_otorgar=otorga)

        # ---------- Autorizaciones + puntos permitidos ----------
        def autorizar(persona, rol, terreno, puntos, vivienda=None, otorgada_por=None, **extra):
            aut = crear(Autorizacion, persona=persona, rol=rol, terreno=terreno, vivienda=vivienda,
                        otorgada_por=otorgada_por, **extra)
            for clave in puntos:
                crear(AutorizacionPunto, autorizacion=aut, punto_acceso=pa[clave])
            return aut

        hoy = timezone.localdate()
        a = {}
        # Ana: propietaria admin de dos deptos en Torre A
        a["ana_a101"] = autorizar(p["ana"], r["propietario_admin"], robles,
                                  ["peatonal_norte", "reja_vehicular", "porton_sur", "hall_a", "puerta_a101"], v["A-101"])
        a["ana_a102"] = autorizar(p["ana"], r["propietario_admin"], robles,
                                  ["peatonal_norte", "reja_vehicular", "hall_a", "puerta_a102"], v["A-102"])
        # Situación: un propietario administrador incorpora a un arrendatario
        a["benja_a101"] = autorizar(p["benja"], r["arrendatario"], robles,
                                    ["peatonal_norte", "reja_vehicular", "hall_a", "puerta_a101"], v["A-101"],
                                    otorgada_por=p["ana"])
        # Situación: persona con viviendas en dos terrenos (Benja: arrendatario en Los Robles, dueño en El Bosque)
        a["benja_casa3"] = autorizar(p["benja"], r["propietario_admin"], bosque,
                                     ["porton_bosque", "peatonal_bosque"], v["Casa 3"])
        # Situación: trabajador sin vivienda, con acceso a 2 edificios
        a["sofi"] = autorizar(p["sofi"], r["trabajador"], robles,
                              ["peatonal_norte", "hall_a", "hall_b"], otorgada_por=p["carlos"])
        # Pedro y su hija (residente: convive sin ser dueña ni arrendataria)
        a["pedro"] = autorizar(p["pedro"], r["propietario_admin"], bosque,
                               ["porton_bosque", "peatonal_bosque", "puerta_casa7"], v["Casa 7"])
        a["ema"] = autorizar(p["ema"], r["residente"], bosque,
                             ["peatonal_bosque", "puerta_casa7"], v["Casa 7"], otorgada_por=p["pedro"])
        # Valentina y un arrendatario cuyo contrato ya venció
        a["vale"] = autorizar(p["vale"], r["propietario_admin"], robles,
                              ["peatonal_norte", "reja_vehicular", "hall_b"], v["B-201"])
        a["lucas"] = autorizar(p["lucas"], r["arrendatario"], robles,
                               ["peatonal_norte", "hall_b"], v["B-201"], otorgada_por=p["vale"],
                               fecha_inicio=hoy - timedelta(days=365), fecha_fin=hoy - timedelta(days=10))

        # ---------- Credenciales ----------
        c = {}
        for clave, uid, persona, tipo, estado in [
            ("ana_t", "04A1B2C3D4", "ana", "tarjeta", "activa"),
            ("ana_l", "04A1B2C3D5", "ana", "llavero", "activa"),
            ("benja_t", "04B7E8F9A0", "benja", "tarjeta", "activa"),
            ("sofi_t", "04C1D2E3F4", "sofi", "tarjeta", "activa"),
            ("pedro_t", "04D5E6F7A8", "pedro", "tarjeta", "activa"),
            ("ema_l", "04E9F0A1B2", "ema", "llavero", "activa"),
            ("vale_t", "04F3A4B5C6", "vale", "tarjeta", "activa"),
            ("lucas_t", "04A7B8C9D0", "lucas", "tarjeta", "bloqueada"),
            ("carlos_t", "04B1C2D3E4", "carlos", "tarjeta", "activa"),
        ]:
            c[clave] = crear(Credencial, uid=uid, persona=p[persona], tipo=tipo, estado=estado)

        # ---------- Historial de intentos (ayer) ----------
        ayer = hoy - timedelta(days=1)
        tz = timezone.get_current_timezone()

        def cuando(h, m):
            return timezone.make_aware(datetime(ayer.year, ayer.month, ayer.day, h, m), tz)

        def intento(h, m, punto, medio, resultado, persona=None, cred=None, uid=None, aut=None,
                    motivo=None, sentido="entrada", distancia=None, apertura=None):
            reg = crear(RegistroAcceso, fecha_hora=cuando(h, m), punto_acceso=pa[punto], medio=medio,
                        resultado=resultado, persona=p.get(persona), credencial=c.get(cred),
                        uid_recibido=uid or (c[cred].uid if cred else None), autorizacion=a.get(aut),
                        motivo=motivo, sentido=sentido, distancia_m=distancia)
            if apertura:
                crear(AperturaDispositivo, registro=reg, fecha_hora=cuando(h, m) + timedelta(seconds=2), estado=apertura)
            return reg

        intento(7, 55, "peatonal_norte", "rfid", "permitido", "sofi", "sofi_t", aut="sofi", apertura="abrio")
        intento(8, 2, "hall_b", "rfid", "permitido", "sofi", "sofi_t", aut="sofi", apertura="abrio")
        # Situación: entra por un acceso y la deniegan en otro
        intento(8, 30, "reja_vehicular", "rfid", "denegado", "sofi", "sofi_t", motivo="Punto de acceso no autorizado")
        intento(8, 45, "puerta_a101", "rfid", "permitido", "ana", "ana_t", aut="ana_a101", sentido="salida", apertura="abrio")
        intento(9, 10, "reja_vehicular", "app", "permitido", "benja", aut="benja_a101", distancia=Decimal("12.50"),
                apertura="sin_respuesta")
        # Credencial desconocida: se guarda el UID recibido y el motivo
        intento(13, 20, "peatonal_norte", "rfid", "denegado", uid="04FFFFFFFF", motivo="Credencial desconocida")
        intento(14, 5, "peatonal_norte", "rfid", "denegado", "lucas", "lucas_t", motivo="Credencial bloqueada")
        intento(14, 7, "peatonal_norte", "app", "denegado", "lucas", motivo="Autorización vencida", distancia=Decimal("8.00"))
        intento(18, 40, "peatonal_bosque", "rfid", "permitido", "ema", "ema_l", aut="ema", apertura="abrio")
        intento(18, 41, "puerta_casa7", "rfid", "permitido", "ema", "ema_l", aut="ema", apertura="abrio")
        intento(19, 15, "porton_bosque", "app", "denegado", "ema", motivo="Punto de acceso no autorizado",
                distancia=Decimal("5.20"))
        intento(20, 0, "porton_bosque", "app", "permitido", "benja", aut="benja_casa3", distancia=Decimal("30.00"),
                apertura="abrio")
        intento(21, 30, "peatonal_bosque", "app", "denegado", "pedro", motivo="Fuera del rango de cercanía",
                distancia=Decimal("850.00"))

        resumen = {
            "personas": Persona.objects.count(), "credenciales": Credencial.objects.count(),
            "terrenos": Terreno.objects.count(), "edificios": Edificio.objects.count(),
            "viviendas": Vivienda.objects.count(), "roles": Rol.objects.count(),
            "puntos de acceso": PuntoAcceso.objects.count(), "autorizaciones": Autorizacion.objects.count(),
            "puntos permitidos": AutorizacionPunto.objects.count(), "registros": RegistroAcceso.objects.count(),
            "aperturas": AperturaDispositivo.objects.count(),
        }
        for k, n in resumen.items():
            self.stdout.write(f"  {k:<18} {n}")
        self.stdout.write(self.style.SUCCESS("Datos ficticios cargados."))
