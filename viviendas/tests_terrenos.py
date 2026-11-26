import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APITestCase

from personas.models import Persona

from .models import Edificio, Terreno, Vivienda

URL = "/api/terrenos/"


class TerrenoCrudTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos", stdout=io.StringIO())
        cls.carlos = Persona.objects.get(email="carlos@smartconnect.test")
        cls.ana = Persona.objects.get(email="ana@smartconnect.test")
        cls.robles = Terreno.objects.get(codigo="TR-ROBLES")

    def setUp(self):
        # Estas pruebas revisan el CRUD, no la seguridad: entran como personal de SmartConnect
        self.client.force_authenticate(get_user_model().objects.get(username="soporte"))

    def datos(self, **extra):
        base = {"codigo": "tr-lagos", "nombre": "Condominio Los Lagos", "direccion": "Av. Los Lagos 45, Macul",
                "administrador": self.ana.pk, "latitud": "-33.500000", "longitud": "-70.600000"}
        base.update(extra)
        return base

    def test_listar_y_filtrar(self):
        self.assertEqual(len(self.client.get(URL).json()), 2)
        self.assertEqual(len(self.client.get(URL, {"buscar": "bosque"}).json()), 1)
        self.assertEqual(len(self.client.get(URL, {"administrador": self.carlos.pk}).json()), 2)
        self.assertEqual(len(self.client.get(URL, {"administrador": self.ana.pk}).json()), 0)
        self.assertEqual(len(self.client.get(URL, {"activo": "false"}).json()), 0)

    def test_detalle_muestra_resumen(self):
        r = self.client.get(f"{URL}{self.robles.pk}/")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["administrador_nombre"], "Carlos Muñoz Herrera")
        self.assertEqual(d["edificios"], ["Torre A", "Torre B"])
        self.assertEqual(d["total_viviendas"], 3)
        self.assertEqual(d["total_puntos_acceso"], 7)

    def test_crear_normaliza_codigo(self):
        r = self.client.post(URL, self.datos(), format="json")
        self.assertEqual(r.status_code, 201, r.json())
        self.assertEqual(r.json()["codigo"], "TR-LAGOS")
        self.assertTrue(r.json()["activo"])
        self.assertEqual(r.json()["total_viviendas"], 0)

    def test_codigo_repetido_sin_distinguir_mayusculas(self):
        r = self.client.post(URL, self.datos(codigo="tr-robles"), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("codigo", r.json())
        self.assertEqual(Terreno.objects.count(), 2)

    def test_validaciones(self):
        casos = {
            "administrador": self.datos(administrador=9999),
            "latitud": self.datos(latitud="95.000000"),
            "longitud": self.datos(longitud="-181.000000"),
            "nombre": self.datos(nombre="   "),
        }
        for campo, datos in casos.items():
            r = self.client.post(URL, datos, format="json")
            self.assertEqual(r.status_code, 400, campo)
            self.assertIn(campo, r.json())
        self.assertEqual(Terreno.objects.count(), 2)

    def test_administrador_inactivo_y_coordenadas_incompletas(self):
        Persona.objects.filter(pk=self.ana.pk).update(activo=False)
        r = self.client.post(URL, self.datos(), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("administrador", r.json())
        Persona.objects.filter(pk=self.ana.pk).update(activo=True)
        datos = self.datos()
        del datos["longitud"]
        r = self.client.post(URL, datos, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("longitud", r.json())

    def test_put_patch_delete(self):
        r = self.client.post(URL, self.datos(), format="json")
        url = f"{URL}{r.json()['id']}/"
        r = self.client.put(url, self.datos(codigo="TR-LAGOS", nombre="Los Lagos II", administrador=self.carlos.pk,
                                            activo=True), format="json")
        self.assertEqual(r.status_code, 200, r.json())
        self.assertEqual(r.json()["administrador_nombre"], "Carlos Muñoz Herrera")
        r = self.client.patch(url, {"activo": False}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["activo"])
        self.assertEqual(r.json()["nombre"], "Los Lagos II")
        r = self.client.patch(url, {"latitud": None}, format="json")  # dejaría la longitud sola
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_borrar_terreno_con_datos_da_409(self):
        r = self.client.delete(f"{URL}{self.robles.pk}/")
        self.assertEqual(r.status_code, 409)
        self.assertIn("viviendas", r.json()["relacionados"])
        self.assertTrue(Terreno.objects.filter(pk=self.robles.pk).exists())


class ViviendaCodigoRepetidoTests(APITestCase):
    """Un código de vivienda repetido en minúsculas debe dar 400 (antes daba error 500)."""

    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos", stdout=io.StringIO())

    def setUp(self):
        # Estas pruebas revisan el CRUD, no la seguridad: entran como personal de SmartConnect
        self.client.force_authenticate(get_user_model().objects.get(username="soporte"))

    def test_codigo_repetido_da_400(self):
        robles = Terreno.objects.get(codigo="TR-ROBLES")
        torre_a = Edificio.objects.get(nombre="Torre A")
        antes = Vivienda.objects.count()
        r = self.client.post("/api/viviendas/", {"codigo": "lr-a-101", "tipo": "departamento", "numero": "9",
                                                 "terreno": robles.pk, "edificio": torre_a.pk}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("codigo", r.json())
        self.assertEqual(Vivienda.objects.count(), antes)
