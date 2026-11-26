"""Pruebas de seguridad: login JWT, 401 sin token, 403 fuera de alcance y listados filtrados."""
import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient, APITestCase

from personas.models import Persona
from viviendas.models import Edificio, Terreno, Vivienda

from .models import PuntoAcceso

CLAVE = "smart1234"
RUTAS = ["/api/personas/", "/api/viviendas/", "/api/terrenos/", "/api/edificios/", "/api/puntos-acceso/"]


class Base(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos", stdout=io.StringIO())
        cls.robles = Terreno.objects.get(codigo="TR-ROBLES")
        cls.bosque = Terreno.objects.get(codigo="TR-BOSQUE")
        cls.torre_a = Edificio.objects.get(nombre="Torre A")
        cls.a101 = Vivienda.objects.get(codigo="LR-A-101")
        cls.casa7 = Vivienda.objects.get(codigo="EB-C-07")
        cls.persona = {p.email.split("@")[0]: p for p in Persona.objects.all()}

    def token(self, username, clave=CLAVE):
        return APIClient().post("/api/token/", {"username": username, "password": clave}, format="json")

    def entrar(self, username):
        """Hace login de verdad (POST /api/token/) y usa el access en las siguientes peticiones."""
        r = self.token(username)
        self.assertEqual(r.status_code, 200, r.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")

    def ids(self, url, **params):
        r = self.client.get(url, params)
        self.assertEqual(r.status_code, 200, r.content)
        return sorted(x["id"] for x in r.json())


class LoginJwtTests(Base):
    def test_login_devuelve_access_y_refresh(self):
        r = self.token("ana")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), {"access", "refresh"})

    def test_clave_incorrecta_o_cuenta_inexistente_da_401(self):
        self.assertEqual(self.token("ana", "otra-clave").status_code, 401)
        self.assertEqual(self.token("nadie").status_code, 401)

    def test_cuenta_inactiva_no_entra(self):
        get_user_model().objects.filter(username="ana").update(is_active=False)
        self.assertEqual(self.token("ana").status_code, 401)

    def test_refresh_entrega_un_access_nuevo(self):
        tokens = self.token("ana").json()
        r = APIClient().post("/api/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.json())
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        self.assertEqual(self.client.get("/api/viviendas/").status_code, 200)

    def test_refresh_invalido_da_401(self):
        r = APIClient().post("/api/token/refresh/", {"refresh": "no-es-un-token"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_el_refresh_no_sirve_como_access(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token('ana').json()['refresh']}")
        self.assertEqual(self.client.get("/api/viviendas/").status_code, 401)


class SinTokenTests(Base):
    def test_rutas_protegidas_responden_401(self):
        for url in RUTAS:
            self.assertEqual(self.client.get(url).status_code, 401, url)
            self.assertEqual(self.client.get(f"{url}1/").status_code, 401, url)
            self.assertEqual(self.client.post(url, {}, format="json").status_code, 401, url)
            self.assertEqual(self.client.delete(f"{url}1/").status_code, 401, url)

    def test_token_falso_da_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer abc.def.ghi")
        for url in RUTAS:
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_sin_token_no_cambia_la_base(self):
        antes = Vivienda.objects.count()
        self.client.post("/api/viviendas/", {"codigo": "X", "tipo": "casa", "numero": "1",
                                             "terreno": self.bosque.pk}, format="json")
        self.client.delete(f"/api/viviendas/{self.a101.pk}/")
        self.assertEqual(Vivienda.objects.count(), antes)


class ListadosFiltradosTests(Base):
    def codigos(self, url):
        return sorted(x["codigo"] for x in self.client.get(url).json())

    def test_personal_ve_todo(self):
        self.entrar("soporte")
        self.assertEqual(len(self.ids("/api/viviendas/")), 5)
        self.assertEqual(len(self.ids("/api/terrenos/")), 2)
        self.assertEqual(len(self.ids("/api/personas/")), 8)
        self.assertEqual(len(self.ids("/api/puntos-acceso/")), 10)

    def test_administrador_de_terrenos_ve_sus_terrenos(self):
        self.entrar("carlos")      # administra Los Robles y El Bosque
        self.assertEqual(len(self.ids("/api/viviendas/")), 5)
        self.assertEqual(len(self.ids("/api/terrenos/")), 2)
        self.assertEqual(len(self.ids("/api/personas/")), 8)
        self.assertEqual(len(self.ids("/api/puntos-acceso/")), 10)
        self.assertEqual(len(self.ids("/api/edificios/")), 2)

    def test_propietario_admin_ve_sus_viviendas_y_su_gente(self):
        self.entrar("ana")         # propietaria admin de A-101 y A-102
        self.assertEqual(self.codigos("/api/viviendas/"), ["LR-A-101", "LR-A-102"])
        self.assertEqual(self.codigos("/api/terrenos/"), ["TR-ROBLES"])
        nombres = sorted(x["email"] for x in self.client.get("/api/personas/").json())
        self.assertEqual(nombres, ["ana@smartconnect.test", "benja@smartconnect.test"])
        self.assertEqual(len(self.ids("/api/puntos-acceso/")), 6)   # solo los permitidos a Ana

    def test_persona_con_viviendas_en_dos_terrenos(self):
        self.entrar("benja")       # arrendatario en A-101 y propietario admin de la Casa 3
        self.assertEqual(self.codigos("/api/viviendas/"), ["EB-C-03", "LR-A-101"])
        self.assertEqual(self.codigos("/api/terrenos/"), ["TR-BOSQUE", "TR-ROBLES"])

    def test_residente_solo_ve_lo_suyo(self):
        self.entrar("ema")
        self.assertEqual(self.codigos("/api/viviendas/"), ["EB-C-07"])
        self.assertEqual([x["email"] for x in self.client.get("/api/personas/").json()], ["ema@smartconnect.test"])
        self.assertEqual(len(self.ids("/api/puntos-acceso/")), 2)

    def test_trabajador_ve_el_terreno_pero_no_viviendas(self):
        self.entrar("sofi")        # autorización de terreno, sin vivienda
        self.assertEqual(self.codigos("/api/terrenos/"), ["TR-ROBLES"])
        self.assertEqual(self.ids("/api/viviendas/"), [])
        self.assertEqual(len(self.ids("/api/puntos-acceso/")), 3)
        self.assertEqual(len(self.ids("/api/edificios/")), 2)

    def test_autorizacion_vencida_no_da_alcance(self):
        self.entrar("lucas")       # su arrendamiento venció hace 10 días
        self.assertEqual(self.ids("/api/viviendas/"), [])
        self.assertEqual(self.ids("/api/terrenos/"), [])
        self.assertEqual(self.ids("/api/puntos-acceso/"), [])

    def test_cuenta_sin_persona_no_ve_nada(self):
        get_user_model().objects.create_user("sin_persona", password=CLAVE)
        self.entrar("sin_persona")
        for url in RUTAS:
            self.assertEqual(self.ids(url), [], url)

    def test_persona_desactivada_pierde_alcance(self):
        Persona.objects.filter(pk=self.persona["ana"].pk).update(activo=False)
        self.entrar("ana")
        self.assertEqual(self.ids("/api/viviendas/"), [])


class Alcance403Tests(Base):
    def test_detalle_fuera_de_alcance_da_403(self):
        self.entrar("pedro")       # solo tiene la Casa 7 en El Bosque
        self.assertEqual(self.client.get(f"/api/viviendas/{self.casa7.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/viviendas/{self.a101.pk}/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/terrenos/{self.robles.pk}/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/personas/{self.persona['ana'].pk}/").status_code, 403)
        reja = PuntoAcceso.objects.get(nombre="Reja Vehicular")
        self.assertEqual(self.client.get(f"/api/puntos-acceso/{reja.pk}/").status_code, 403)

    def test_propietario_no_administra_terrenos_ni_viviendas_ajenas(self):
        self.entrar("ana")
        antes = (Terreno.objects.count(), Vivienda.objects.count())
        r = self.client.post("/api/terrenos/", {"codigo": "TR-X", "nombre": "X", "direccion": "Y",
                                                "administrador": self.persona["ana"].pk}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/viviendas/", {"codigo": "LR-A-103", "tipo": "departamento", "numero": "103",
                                                 "terreno": self.robles.pk, "edificio": self.torre_a.pk}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.patch(f"/api/viviendas/{self.a101.pk}/", {"activa": False}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/viviendas/{self.a101.pk}/").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/terrenos/{self.robles.pk}/").status_code, 403)
        self.assertEqual((Terreno.objects.count(), Vivienda.objects.count()), antes)
        self.a101.refresh_from_db()
        self.assertTrue(self.a101.activa)

    def test_administrador_gestiona_su_terreno_con_resultado_persistido(self):
        self.entrar("carlos")
        r = self.client.post("/api/viviendas/", {"codigo": "lr-a-103", "tipo": "departamento", "numero": "103",
                                                 "terreno": self.robles.pk, "edificio": self.torre_a.pk}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(Vivienda.objects.filter(codigo="LR-A-103").exists())
        r = self.client.patch(f"/api/terrenos/{self.robles.pk}/", {"nombre": "Los Robles II"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.robles.refresh_from_db()
        self.assertEqual(self.robles.nombre, "Los Robles II")
        r = self.client.post("/api/puntos-acceso/", {"nombre": "Portón Oeste", "tipo": "vehicular",
                                                     "terreno": self.robles.pk}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.client.delete(f"/api/puntos-acceso/{r.json()['id']}/").status_code, 204)

    def test_administrador_no_toca_terrenos_de_otro(self):
        ajeno = Terreno.objects.create(codigo="TR-OTRO", nombre="Otro", direccion="Calle 1",
                                       administrador=self.persona["ana"])
        self.entrar("carlos")
        antes = (Vivienda.objects.count(), PuntoAcceso.objects.count())
        r = self.client.post("/api/viviendas/", {"codigo": "OT-C-1", "tipo": "casa", "numero": "1",
                                                 "terreno": ajeno.pk}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/puntos-acceso/", {"nombre": "Portón", "tipo": "vehicular", "terreno": ajeno.pk},
                             format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.patch(f"/api/terrenos/{ajeno.pk}/", {"nombre": "Mío"}, format="json").status_code, 403)
        # tampoco puede mover una de sus viviendas a un terreno que no administra
        r = self.client.patch(f"/api/viviendas/{self.casa7.pk}/", {"terreno": ajeno.pk}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual((Vivienda.objects.count(), PuntoAcceso.objects.count()), antes)
        # el administrador de ese terreno sí puede
        self.entrar("ana")
        r = self.client.post("/api/viviendas/", {"codigo": "OT-C-1", "tipo": "casa", "numero": "1",
                                                 "terreno": ajeno.pk}, format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_solo_el_personal_crea_borra_y_reasigna_terrenos(self):
        self.entrar("carlos")
        r = self.client.post("/api/terrenos/", {"codigo": "TR-X", "nombre": "X", "direccion": "Y",
                                                "administrador": self.persona["carlos"].pk}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.delete(f"/api/terrenos/{self.robles.pk}/").status_code, 403)
        r = self.client.patch(f"/api/terrenos/{self.robles.pk}/", {"administrador": self.persona["ana"].pk}, format="json")
        self.assertEqual(r.status_code, 403)
        self.robles.refresh_from_db()
        self.assertEqual(self.robles.administrador_id, self.persona["carlos"].pk)
        self.entrar("soporte")
        r = self.client.post("/api/terrenos/", {"codigo": "TR-X", "nombre": "X", "direccion": "Y",
                                                "administrador": self.persona["carlos"].pk}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.client.delete(f"/api/terrenos/{r.json()['id']}/").status_code, 204)

    def test_trabajador_no_modifica_puntos(self):
        self.entrar("sofi")
        peatonal = PuntoAcceso.objects.get(nombre="Peatonal Norte")
        self.assertEqual(self.client.get(f"/api/puntos-acceso/{peatonal.pk}/").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/puntos-acceso/{peatonal.pk}/", {"activo": False}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/puntos-acceso/{peatonal.pk}/").status_code, 403)
        peatonal.refresh_from_db()
        self.assertTrue(peatonal.activo)

    def test_personas_cada_uno_edita_lo_suyo(self):
        self.entrar("ema")
        mia = self.persona["ema"]
        r = self.client.patch(f"/api/personas/{mia.pk}/", {"telefono": "+56 9 1212 1212"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        # no puede cambiar su RUT ni desactivarse a sí misma, ni tocar a otros ni borrarse
        self.assertEqual(self.client.patch(f"/api/personas/{mia.pk}/", {"rut": "18765432-7"}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(f"/api/personas/{mia.pk}/", {"activo": False}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(f"/api/personas/{self.persona['pedro'].pk}/", {"telefono": "1"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/personas/{mia.pk}/").status_code, 403)
        mia.refresh_from_db()
        self.assertEqual(mia.telefono, "+56 9 1212 1212")
        self.assertTrue(mia.activo)

    def test_quien_puede_registrar_personas(self):
        datos = {"rut": "18765432-7", "nombres": "Marta", "apellidos": "Lillo", "email": "marta@smartconnect.test"}
        self.entrar("ema")                                   # una residente no registra personas
        self.assertEqual(self.client.post("/api/personas/", datos, format="json").status_code, 403)
        self.assertFalse(Persona.objects.filter(email="marta@smartconnect.test").exists())
        self.entrar("ana")                                   # una propietaria administradora sí
        self.assertEqual(self.client.post("/api/personas/", datos, format="json").status_code, 201)

    def test_cuenta_sin_persona_no_puede_actuar(self):
        get_user_model().objects.create_user("sin_persona", password=CLAVE)
        self.entrar("sin_persona")
        self.assertEqual(self.client.get(f"/api/viviendas/{self.a101.pk}/").status_code, 403)
        self.assertEqual(self.client.post("/api/personas/", {}, format="json").status_code, 403)
        self.assertEqual(self.client.post("/api/viviendas/", {}, format="json").status_code, 403)
