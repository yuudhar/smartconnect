"""Operación del negocio: asignar una persona a una vivienda con su tipo de participación."""
import io
from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from personas.models import Persona
from viviendas.models import Terreno, Vivienda

from .models import Autorizacion, AutorizacionPunto, PuntoAcceso

URL = "/api/asignaciones/"
CLAVE = "smart1234"


class AsignacionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos", stdout=io.StringIO())
        cls.persona = {p.email.split("@")[0]: p for p in Persona.objects.all()}
        cls.viv = {v.codigo: v for v in Vivienda.objects.all()}
        cls.punto = {p.nombre: p for p in PuntoAcceso.objects.all()}

    def entrar(self, username):
        r = APIClient().post("/api/token/", {"username": username, "password": CLAVE}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")

    def estado(self):
        """Foto de la base para comprobar que un rechazo no cambia nada."""
        return (Autorizacion.objects.count(), AutorizacionPunto.objects.count())

    def datos(self, persona="lucas", vivienda="LR-A-102", rol="residente", puntos=("Peatonal Norte", "Puerta A-102"), **extra):
        d = {"persona": self.persona[persona].pk, "vivienda": self.viv[vivienda].pk, "rol": rol,
             "puntos_acceso": [self.punto[n].pk for n in puntos]}
        d.update(extra)
        return d

    # ------------------------------------------------------------------ caso válido

    def test_propietario_admin_asigna_y_queda_guardado(self):
        self.entrar("ana")
        antes = self.estado()
        r = self.client.post(URL, self.datos(), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual((d["rol"], d["vivienda_codigo"], d["terreno_nombre"]),
                         ("residente", "LR-A-102", "Condominio Los Robles"))
        self.assertEqual(d["otorgada_por_nombre"], "Ana Rojas Pinto")
        self.assertTrue(d["activa"] and d["vigente"])
        self.assertEqual(self.estado(), (antes[0] + 1, antes[1] + 2))
        # resultado persistido: relación, quién la otorgó y puntos permitidos
        aut = Autorizacion.objects.get(pk=d["id"])
        self.assertEqual((aut.persona, aut.vivienda.codigo, aut.rol.nombre, aut.otorgada_por),
                         (self.persona["lucas"], "LR-A-102", "residente", self.persona["ana"]))
        self.assertEqual(sorted(p.nombre for p in aut.puntos.all()), ["Peatonal Norte", "Puerta A-102"])
        # y el detalle y el listado la muestran
        self.assertEqual(self.client.get(f"{URL}{aut.pk}/").status_code, 200)
        self.assertIn(aut.pk, [x["id"] for x in self.client.get(URL, {"vivienda": self.viv["LR-A-102"].pk}).json()])

    def test_sin_puntos_queda_vinculada_sin_accesos(self):
        self.entrar("ana")
        r = self.client.post(URL, self.datos(puntos=()), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["puntos_acceso"], [])

    def test_el_persona_nueva_asignada_ya_ve_su_vivienda(self):
        self.entrar("ana")
        self.client.post(URL, self.datos(), format="json")
        self.entrar("lucas")
        codigos = [v["codigo"] for v in self.client.get("/api/viviendas/").json()]
        self.assertEqual(codigos, ["LR-A-102"])

    def test_contrato_vencido_permite_una_nueva_asignacion(self):
        self.entrar("vale")        # Lucas tenía un arriendo vencido en B-201
        r = self.client.post(URL, self.datos(vivienda="LR-B-201", rol="arrendatario",
                                             puntos=("Peatonal Norte", "Hall Torre B")), format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_personal_asigna_el_primer_propietario_admin(self):
        robles = Terreno.objects.get(codigo="TR-ROBLES")
        nueva = Vivienda.objects.create(codigo="LR-A-103", tipo="departamento", numero="103", terreno=robles,
                                        edificio=self.viv["LR-A-101"].edificio)
        self.entrar("soporte")
        r = self.client.post(URL, {"persona": self.persona["lucas"].pk, "vivienda": nueva.pk,
                                   "rol": "propietario_admin"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(r.json()["otorgada_por"])     # la cuenta del personal no es una persona

    # ------------------------------------------------------------------ autoridad (401 y 403)

    def test_sin_token_401(self):
        antes = self.estado()
        self.assertEqual(self.client.post(URL, self.datos(), format="json").status_code, 401)
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.assertEqual(self.estado(), antes)

    def test_quien_no_es_propietario_admin_de_esa_vivienda_recibe_403(self):
        antes = self.estado()
        for quien, vivienda in (("ana", "LR-B-201"),       # administra otras viviendas, no esta
                                ("benja", "LR-A-101"),     # es arrendatario de esta vivienda
                                ("pedro", "LR-A-102"),     # propietario admin, pero de otro terreno
                                ("ema", "EB-C-07"),        # residente
                                ("sofi", "LR-A-101"),      # trabajadora
                                ("carlos", "LR-A-101")):   # administra el terreno, no las personas de la vivienda
            self.entrar(quien)
            r = self.client.post(URL, self.datos(vivienda=vivienda, puntos=("Peatonal Norte",)), format="json")
            self.assertEqual(r.status_code, 403, f"{quien} en {vivienda}: {r.content}")
        self.assertEqual(self.estado(), antes)

    def test_autoridad_vencida_o_revocada_ya_no_asigna(self):
        Autorizacion.objects.filter(persona=self.persona["ana"], vivienda=self.viv["LR-A-102"]).update(activa=False)
        self.entrar("ana")
        antes = self.estado()
        self.assertEqual(self.client.post(URL, self.datos(), format="json").status_code, 403)
        self.assertEqual(self.estado(), antes)

    # ------------------------------------------------------------------ reglas (400) que no tocan la base

    def test_rechazos_no_cambian_la_base(self):
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        Persona.objects.filter(pk=self.persona["ema"].pk).update(activo=False)
        casos = {
            "persona": [self.datos(persona="benja", vivienda="LR-A-101", rol="residente",     # ya vinculado
                                   puntos=("Peatonal Norte",)),
                        self.datos(persona="ema")],                                           # desactivada
            "rol": [self.datos(rol="trabajador"),                                             # rol del terreno
                    self.datos(rol="propietario_admin")],                                     # ya hay uno
            "fecha_fin": [self.datos(fecha_inicio=manana, fecha_fin=ayer),
                          self.datos(fecha_fin=ayer)],
            "puntos_acceso": [self.datos(puntos=("Portón Principal",)),                       # otro terreno
                              self.datos(puntos=("Puerta A-101",)),                           # puerta de otra vivienda
                              self.datos(puntos=("Hall Torre B",)),                           # Ana no tiene ese acceso
                              self.datos(puntos=("Portón Sur",))],                            # Ana no lo tiene en A-102
        }
        self.entrar("ana")
        antes = self.estado()
        for campo, lista in casos.items():
            for datos in lista:
                r = self.client.post(URL, datos, format="json")
                self.assertEqual(r.status_code, 400, f"{campo}: {datos} -> {r.content}")
                self.assertIn(campo, r.json())
                self.assertEqual(self.estado(), antes, campo)

    def test_no_se_asigna_dos_veces_la_misma_persona(self):
        self.entrar("ana")
        self.assertEqual(self.client.post(URL, self.datos(), format="json").status_code, 201)
        antes = self.estado()
        r = self.client.post(URL, self.datos(rol="arrendatario"), format="json")   # otro rol, misma vivienda
        self.assertEqual(r.status_code, 400)
        self.assertIn("ya está asignada", r.json()["persona"][0])
        self.assertEqual(self.estado(), antes)

    def test_vivienda_desactivada_y_datos_inexistentes(self):
        Vivienda.objects.filter(pk=self.viv["LR-A-102"].pk).update(activa=False)
        self.entrar("ana")
        antes = self.estado()
        self.assertEqual(self.client.post(URL, self.datos(), format="json").status_code, 400)
        r = self.client.post(URL, {"persona": 9999, "vivienda": self.viv["LR-A-101"].pk, "rol": "residente"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(URL, self.datos(vivienda="LR-A-101", rol="inventado", puntos=()), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.estado(), antes)

    # ------------------------------------------------------------------ consultas y revocación

    def test_listados_segun_alcance(self):
        esperado = {"soporte": 8, "carlos": 8, "ana": 3, "benja": 2, "pedro": 2, "ema": 1, "sofi": 0, "lucas": 1}
        for quien, n in esperado.items():
            self.entrar(quien)
            r = self.client.get(URL)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(r.json()), n, quien)
        # Lucas ve su propia asignación, pero está vencida
        self.assertFalse(r.json()[0]["vigente"])

    def test_detalle_ajeno_da_403(self):
        ana_a101 = Autorizacion.objects.get(persona=self.persona["ana"], vivienda=self.viv["LR-A-101"])
        self.entrar("pedro")
        self.assertEqual(self.client.get(f"{URL}{ana_a101.pk}/").status_code, 403)
        self.entrar("benja")       # participa en esa vivienda, pero no es el administrador: ve solo lo suyo
        self.assertEqual(self.client.get(f"{URL}{ana_a101.pk}/").status_code, 403)

    def test_filtros(self):
        self.entrar("soporte")
        self.assertEqual(len(self.client.get(URL, {"rol": "residente"}).json()), 1)
        self.assertEqual(len(self.client.get(URL, {"vivienda": self.viv["LR-A-101"].pk}).json()), 2)
        self.assertEqual(len(self.client.get(URL, {"persona": self.persona["benja"].pk}).json()), 2)
        self.assertEqual(len(self.client.get(URL, {"activa": "false"}).json()), 0)

    def test_revocar(self):
        benja_a101 = Autorizacion.objects.get(persona=self.persona["benja"], vivienda=self.viv["LR-A-101"])
        url = f"{URL}{benja_a101.pk}/revocar/"
        self.entrar("benja")                      # el arrendatario no puede revocar
        self.assertEqual(self.client.post(url).status_code, 403)
        self.entrar("vale")                       # otra propietaria admin tampoco
        self.assertEqual(self.client.post(url).status_code, 403)
        benja_a101.refresh_from_db()
        self.assertTrue(benja_a101.activa)
        self.entrar("ana")
        r = self.client.post(url)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["activa"])
        benja_a101.refresh_from_db()
        self.assertFalse(benja_a101.activa)
        self.assertEqual(self.client.post(url).status_code, 400)       # ya estaba revocada
        # sin la asignación, Benja pierde el alcance sobre esa vivienda
        self.entrar("benja")
        self.assertEqual(self.client.get(f"/api/viviendas/{self.viv['LR-A-101'].pk}/").status_code, 403)
        # y Ana puede volver a asignarlo
        self.entrar("ana")
        r = self.client.post(URL, self.datos(persona="benja", vivienda="LR-A-101", rol="arrendatario",
                                             puntos=("Peatonal Norte", "Puerta A-101")), format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_un_propietario_admin_solo_lo_revoca_el_personal(self):
        propia = Autorizacion.objects.get(persona=self.persona["ana"], vivienda=self.viv["LR-A-101"])
        self.entrar("ana")
        self.assertEqual(self.client.post(f"{URL}{propia.pk}/revocar/").status_code, 403)
        self.entrar("soporte")
        self.assertEqual(self.client.post(f"{URL}{propia.pk}/revocar/").status_code, 200)

    def test_asignacion_no_se_edita_ni_se_borra(self):
        aut = Autorizacion.objects.get(persona=self.persona["benja"], vivienda=self.viv["LR-A-101"])
        self.entrar("soporte")
        for metodo in (self.client.put, self.client.patch, self.client.delete):
            self.assertEqual(metodo(f"{URL}{aut.pk}/").status_code, 405)
        self.assertTrue(Autorizacion.objects.filter(pk=aut.pk).exists())
