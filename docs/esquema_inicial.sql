-- SmartConnect · Esquema inicial (SQLite) generado desde las migraciones de Django
-- Regenerar: python manage.py migrate  (las tablas de Django auth/admin se omiten)

CREATE TABLE "accesos_aperturadispositivo" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "fecha_hora" datetime NOT NULL, "estado" varchar(15) NOT NULL, "registro_id" bigint NOT NULL UNIQUE REFERENCES "accesos_registroacceso" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "accesos_autorizacion" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "fecha_inicio" date NOT NULL, "fecha_fin" date NULL, "activa" bool NOT NULL, "otorgada_por_id" bigint NULL REFERENCES "personas_persona" ("id") DEFERRABLE INITIALLY DEFERRED, "persona_id" bigint NOT NULL REFERENCES "personas_persona" ("id") DEFERRABLE INITIALLY DEFERRED, "terreno_id" bigint NOT NULL REFERENCES "viviendas_terreno" ("id") DEFERRABLE INITIALLY DEFERRED, "vivienda_id" bigint NULL REFERENCES "viviendas_vivienda" ("id") DEFERRABLE INITIALLY DEFERRED, "rol_id" bigint NOT NULL REFERENCES "accesos_rol" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "autorizacion_fecha_fin_posterior" CHECK (("fecha_fin" IS NULL OR "fecha_fin" >= ("fecha_inicio"))));

CREATE TABLE "accesos_autorizacionpunto" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "autorizacion_id" bigint NOT NULL REFERENCES "accesos_autorizacion" ("id") DEFERRABLE INITIALLY DEFERRED, "punto_acceso_id" bigint NOT NULL REFERENCES "accesos_puntoacceso" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "autorizacion_punto_unico" UNIQUE ("autorizacion_id", "punto_acceso_id"));

CREATE TABLE "accesos_puntoacceso" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "nombre" varchar(80) NOT NULL, "tipo" varchar(10) NOT NULL, "latitud" decimal NULL, "longitud" decimal NULL, "activo" bool NOT NULL, "edificio_id" bigint NULL REFERENCES "viviendas_edificio" ("id") DEFERRABLE INITIALLY DEFERRED, "terreno_id" bigint NOT NULL REFERENCES "viviendas_terreno" ("id") DEFERRABLE INITIALLY DEFERRED, "vivienda_id" bigint NULL REFERENCES "viviendas_vivienda" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "punto_edificio_o_vivienda_no_ambos" CHECK (("edificio_id" IS NULL OR "vivienda_id" IS NULL)));

CREATE TABLE "accesos_registroacceso" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "fecha_hora" datetime NOT NULL, "sentido" varchar(10) NOT NULL, "medio" varchar(10) NOT NULL, "uid_recibido" varchar(32) NULL, "resultado" varchar(10) NOT NULL, "motivo" varchar(120) NULL, "distancia_m" decimal NULL, "autorizacion_id" bigint NULL REFERENCES "accesos_autorizacion" ("id") DEFERRABLE INITIALLY DEFERRED, "credencial_id" bigint NULL REFERENCES "personas_credencial" ("id") DEFERRABLE INITIALLY DEFERRED, "persona_id" bigint NULL REFERENCES "personas_persona" ("id") DEFERRABLE INITIALLY DEFERRED, "punto_acceso_id" bigint NOT NULL REFERENCES "accesos_puntoacceso" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "accesos_rol" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "nombre" varchar(30) NOT NULL UNIQUE, "descripcion" varchar(120) NOT NULL, "ambito" varchar(10) NOT NULL, "puede_otorgar" bool NOT NULL);

CREATE TABLE "personas_credencial" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "uid" varchar(32) NOT NULL UNIQUE, "tipo" varchar(10) NOT NULL, "estado" varchar(10) NOT NULL, "fecha_emision" date NOT NULL, "persona_id" bigint NOT NULL REFERENCES "personas_persona" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "personas_persona" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "rut" varchar(12) NOT NULL UNIQUE, "nombres" varchar(80) NOT NULL, "apellidos" varchar(80) NOT NULL, "email" varchar(254) NOT NULL UNIQUE, "telefono" varchar(20) NULL, "activo" bool NOT NULL, "creado_en" datetime NOT NULL);

CREATE TABLE "viviendas_edificio" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "nombre" varchar(50) NOT NULL, "pisos" smallint unsigned NOT NULL CHECK ("pisos" >= 0), "activo" bool NOT NULL, "terreno_id" bigint NOT NULL REFERENCES "viviendas_terreno" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "edificio_nombre_unico_por_terreno" UNIQUE ("terreno_id", "nombre"));

CREATE TABLE "viviendas_terreno" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "codigo" varchar(20) NOT NULL UNIQUE, "nombre" varchar(80) NOT NULL, "direccion" varchar(150) NOT NULL, "latitud" decimal NULL, "longitud" decimal NULL, "activo" bool NOT NULL, "creado_en" datetime NOT NULL, "administrador_id" bigint NOT NULL REFERENCES "personas_persona" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "viviendas_vivienda" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "codigo" varchar(20) NOT NULL UNIQUE, "tipo" varchar(12) NOT NULL, "numero" varchar(20) NOT NULL, "activa" bool NOT NULL, "edificio_id" bigint NULL REFERENCES "viviendas_edificio" ("id") DEFERRABLE INITIALLY DEFERRED, "terreno_id" bigint NOT NULL REFERENCES "viviendas_terreno" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "vivienda_casa_sin_edificio_depto_con_edificio" CHECK ((("edificio_id" IS NULL AND "tipo" = 'casa') OR ("edificio_id" IS NOT NULL AND "tipo" = 'departamento'))));

CREATE INDEX "accesos_autorizacion_otorgada_por_id_f8d37d77" ON "accesos_autorizacion" ("otorgada_por_id");

CREATE INDEX "accesos_autorizacion_persona_id_2ea589ef" ON "accesos_autorizacion" ("persona_id");

CREATE INDEX "accesos_autorizacion_rol_id_37b74209" ON "accesos_autorizacion" ("rol_id");

CREATE INDEX "accesos_autorizacion_terreno_id_983f42b2" ON "accesos_autorizacion" ("terreno_id");

CREATE INDEX "accesos_autorizacion_vivienda_id_66097c7c" ON "accesos_autorizacion" ("vivienda_id");

CREATE INDEX "accesos_autorizacionpunto_autorizacion_id_d0560c59" ON "accesos_autorizacionpunto" ("autorizacion_id");

CREATE INDEX "accesos_autorizacionpunto_punto_acceso_id_73ca14fa" ON "accesos_autorizacionpunto" ("punto_acceso_id");

CREATE INDEX "accesos_puntoacceso_edificio_id_660d5ecd" ON "accesos_puntoacceso" ("edificio_id");

CREATE INDEX "accesos_puntoacceso_terreno_id_b8b792b0" ON "accesos_puntoacceso" ("terreno_id");

CREATE INDEX "accesos_puntoacceso_vivienda_id_f5cf4fd5" ON "accesos_puntoacceso" ("vivienda_id");

CREATE INDEX "accesos_registroacceso_autorizacion_id_f85432c2" ON "accesos_registroacceso" ("autorizacion_id");

CREATE INDEX "accesos_registroacceso_credencial_id_46d26d06" ON "accesos_registroacceso" ("credencial_id");

CREATE INDEX "accesos_registroacceso_fecha_hora_8a52cc3b" ON "accesos_registroacceso" ("fecha_hora");

CREATE INDEX "accesos_registroacceso_persona_id_ea5a930c" ON "accesos_registroacceso" ("persona_id");

CREATE INDEX "accesos_registroacceso_punto_acceso_id_05c9b73e" ON "accesos_registroacceso" ("punto_acceso_id");

CREATE INDEX "personas_credencial_persona_id_cade5b92" ON "personas_credencial" ("persona_id");

CREATE INDEX "viviendas_edificio_terreno_id_e62a6884" ON "viviendas_edificio" ("terreno_id");

CREATE INDEX "viviendas_terreno_administrador_id_69dfb9d8" ON "viviendas_terreno" ("administrador_id");

CREATE INDEX "viviendas_vivienda_edificio_id_244d88e9" ON "viviendas_vivienda" ("edificio_id");

CREATE INDEX "viviendas_vivienda_terreno_id_ddcccfc0" ON "viviendas_vivienda" ("terreno_id");

