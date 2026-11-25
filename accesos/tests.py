import io

from django.core.management import call_command
from rest_framework.test import APITestCase

from viviendas.models import Edificio, Terreno, Vivienda

from .models import PuntoAcceso

URL = "/api/puntos-acceso/"


class PuntoAccesoCrudTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos", stdout=io.StringIO())
        cls.robles = Terreno.objects.get(codigo="TR-ROBLES")
        cls.bosque = Terreno.objects.get(codigo="TR-BOSQUE")
        cls.torre_a = Edificio.objects.get(nombre="Torre A")
        cls.a101 = Vivienda.objects.get(codigo="LR-A-101")

    def test_listar_y_filtrar(self):
        self.assertEqual(len(self.client.get(URL).json()), 10)
        self.assertEqual(len(self.client.get(URL, {"terreno": self.robles.pk}).json()), 7)
        self.assertEqual(len(self.client.get(URL, {"tipo": "vehicular"}).json()), 3)
        self.assertEqual(len(self.client.get(URL, {"ambito": "vivienda"}).json()), 3)
        self.assertEqual(len(self.client.get(URL, {"ambito": "edificio"}).json()), 2)
        self.assertEqual(len(self.client.get(URL, {"ambito": "terreno"}).json()), 5)
        self.assertEqual(len(self.client.get(URL, {"buscar": "hall"}).json()), 2)

    def test_detalle_muestra_ambito_y_personas(self):
        puerta = PuntoAcceso.objects.get(nombre="Puerta A-101")
        d = self.client.get(f"{URL}{puerta.pk}/").json()
        self.assertEqual(d["ambito"], "vivienda")
        self.assertEqual(d["vivienda_codigo"], "LR-A-101")
        self.assertEqual(sorted(p["nombre"] for p in d["personas_autorizadas"]),
                         ["Ana Rojas Pinto", "Benjamín Soto Lagos"])
        peatonal = PuntoAcceso.objects.get(nombre="Peatonal Norte")
        d = self.client.get(f"{URL}{peatonal.pk}/").json()
        self.assertEqual(d["ambito"], "terreno")
        # Lucas tiene la autorización vencida: no aparece
        self.assertNotIn("Lucas Vera Ortiz", [p["nombre"] for p in d["personas_autorizadas"]])

    def test_crear_en_terreno_edificio_y_vivienda(self):
        base = {"tipo": "puerta", "terreno": self.robles.pk}
        for extra, ambito in (({"nombre": "Portón Oeste", "tipo": "vehicular"}, "terreno"),
                              ({"nombre": "Escalera Torre A", "edificio": self.torre_a.pk}, "edificio"),
                              ({"nombre": "Bodega A-102", "vivienda": self.a101.pk}, "vivienda")):
            r = self.client.post(URL, {**base, **extra}, format="json")
            self.assertEqual(r.status_code, 201, r.json())
            self.assertEqual(r.json()["ambito"], ambito)
            self.assertTrue(r.json()["activo"])

    def test_reglas_de_ubicacion(self):
        casos = [
            # edificio y vivienda a la vez
            ("vivienda", {"nombre": "X1", "tipo": "puerta", "terreno": self.robles.pk,
                          "edificio": self.torre_a.pk, "vivienda": self.a101.pk}),
            # edificio de otro terreno
            ("edificio", {"nombre": "X2", "tipo": "puerta", "terreno": self.bosque.pk,
                          "edificio": self.torre_a.pk}),
            # vivienda de otro terreno
            ("vivienda", {"nombre": "X3", "tipo": "puerta", "terreno": self.bosque.pk,
                          "vivienda": self.a101.pk}),
        ]
        antes = PuntoAcceso.objects.count()
        for campo, datos in casos:
            r = self.client.post(URL, datos, format="json")
            self.assertEqual(r.status_code, 400, datos)
            self.assertIn(campo, r.json())
        self.assertEqual(PuntoAcceso.objects.count(), antes)

    def test_nombre_repetido_y_coordenadas(self):
        antes = PuntoAcceso.objects.count()
        r = self.client.post(URL, {"nombre": "peatonal norte", "tipo": "peatonal", "terreno": self.robles.pk},
                             format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("nombre", r.json())
        # el mismo nombre en otro terreno sí se puede
        r = self.client.post(URL, {"nombre": "Peatonal Norte", "tipo": "peatonal", "terreno": self.bosque.pk},
                             format="json")
        self.assertEqual(r.status_code, 201, r.json())
        r = self.client.post(URL, {"nombre": "Con GPS", "tipo": "peatonal", "terreno": self.bosque.pk,
                                   "latitud": "-33.4"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(URL, {"nombre": "Fuera de rango", "tipo": "peatonal", "terreno": self.bosque.pk,
                                   "latitud": "95", "longitud": "-70"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(PuntoAcceso.objects.count(), antes + 1)

    def test_put_patch_delete(self):
        r = self.client.post(URL, {"nombre": "Portón Oeste", "tipo": "vehicular", "terreno": self.robles.pk},
                             format="json")
        url = f"{URL}{r.json()['id']}/"
        r = self.client.put(url, {"nombre": "Portón Poniente", "tipo": "vehicular", "terreno": self.robles.pk,
                                  "activo": True}, format="json")
        self.assertEqual(r.status_code, 200, r.json())
        r = self.client.patch(url, {"activo": False}, format="json")
        self.assertFalse(r.json()["activo"])
        self.assertEqual(r.json()["nombre"], "Portón Poniente")
        r = self.client.patch(url, {"edificio": self.torre_a.pk, "vivienda": self.a101.pk}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_punto_asignado_no_se_mueve_ni_se_borra(self):
        puerta = PuntoAcceso.objects.get(nombre="Puerta A-101")
        r = self.client.patch(f"{URL}{puerta.pk}/", {"terreno": self.bosque.pk, "vivienda": None}, format="json")
        self.assertEqual(r.status_code, 400)
        puerta.refresh_from_db()
        self.assertEqual(puerta.terreno_id, self.robles.pk)
        # cambiar solo el nombre sí se puede
        r = self.client.patch(f"{URL}{puerta.pk}/", {"nombre": "Puerta principal A-101"}, format="json")
        self.assertEqual(r.status_code, 200, r.json())

    def test_borrar_punto_con_autorizaciones_o_historial_da_409(self):
        asignado = PuntoAcceso.objects.get(nombre="Portón Sur")      # lo tiene Ana, aún sin historial
        r = self.client.delete(f"{URL}{asignado.pk}/")
        self.assertEqual(r.status_code, 409)
        self.assertIn("autorizaciones", r.json()["relacionados"])
        con_historial = PuntoAcceso.objects.get(nombre="Peatonal Norte")
        self.assertEqual(self.client.delete(f"{URL}{con_historial.pk}/").status_code, 409)
        self.assertTrue(PuntoAcceso.objects.filter(pk__in=[asignado.pk, con_historial.pk]).count() == 2)
