# AGENTS.md — Proyecto ADAMS / Portal Sastrería / Migración Odoo

## Contexto general

Este repositorio se usará como base para crear una herramienta puente entre Contífico y Odoo Enterprise 19 para ADAMS.

ADAMS es un negocio retail de ropa formal en Ecuador. Opera con:

- Tienda Urdesa
- Bodega Principal Urdesa
- Tienda Batán
- POS Urdesa Caja 1
- POS Urdesa Caja 2
- POS Batán Caja 1

La empresa principal operativa en Odoo es:

Distribuciones Lortiz Dist Lortiz Dlortiz S.A.

Existe una segunda compañía:

Inmobiliaria Ordefas C. LTDA.

La venta retail se maneja principalmente bajo Distribuciones Lortiz.

## Objetivo del proyecto

Construir una herramienta de migración y apoyo operativo que use la API de Contífico para extraer y transformar información compatible con Odoo 19.

No se debe crear un módulo de Odoo todavía. La prioridad es generar archivos limpios para importar en Odoo.
