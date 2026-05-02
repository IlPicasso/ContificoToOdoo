# ADAMS — Reglas para exportar productos de Contífico a Odoo 19

## Archivo base

La plantilla oficial de Odoo descargada desde:
Ventas → Productos → Productos → Importar registros → Descargar plantilla

Archivo convertido:
`product_product_template.csv`

Columnas exactas de Odoo:

- External ID
- Name
- Product Type
- Internal Reference
- Barcode
- Sales Price
- Cost
- Weight
- Sales Description
- Product Values

## Objetivo

Crear en el portal/proyecto existente una sección o script de migración que consulte la API de Contífico y genere un CSV compatible con Odoo 19 para importar productos y variantes.

No conectar directo a Odoo.
No modificar datos en Contífico.
Solo lectura desde API y generación de archivos revisables.

## Reglas de mapeo

### Campos principales

- `External ID`: ID único generado por el exportador. Debe ser estable y no tener espacios. Ejemplo: `adams_17601_155_s1`.
- `Name`: nombre del producto madre en Odoo. Ejemplo: `Camisa Blanca 17601` o `Terno 210001`.
- `Product Type`: usar `Goods` para productos físicos inventariables.
- `Internal Reference`: SKU de Contífico. Ejemplo: `17601-15.5-S1` o `210001/46`.
- `Barcode`: código de barras original de Contífico.
- `Sales Price`: precio de venta de Contífico.
- `Cost`: costo unitario de Contífico.
- `Weight`: dejar vacío por ahora si no hay dato confiable.
- `Sales Description`: descripción de Contífico si existe; si no, vacío.
- `Product Values`: atributos Odoo en formato `Atributo:Valor,Atributo:Valor`.

## Atributos definidos en Odoo

Atributos que crean variantes:
- `Talla`
- `Manga de Camisa`

Atributos que NO crean variantes:
- `Marca`
- `Color`

Valores especiales:
- `S1` debe convertirse a `S1 - 32/33`
- `S2` debe convertirse a `S2 - 34/35`

## Parsing de SKUs ADAMS

### Camisas formales

Formato de SKU:
`17601-15.5-S1`

Interpretación:
- código madre: `17601`
- producto madre: `Camisa 17601` o usar nombre comercial de Contífico si está disponible
- talla: `15.5`
- manga: `S1 - 32/33`
- Internal Reference: `17601-15.5-S1`

Ejemplo de `Product Values`:
`Talla:15.5,Manga de Camisa:S1 - 32/33,Marca:BRUNO CASSINI,Color:Blanco`

### Ternos

Formato de SKU:
`210001/46`

Interpretación:
- código madre: `210001`
- producto madre: `Terno 210001` o usar nombre comercial de Contífico si está disponible
- talla: `46`
- Internal Reference: `210001/46`

Ejemplo de `Product Values`:
`Talla:46,Marca:BRUNO CASSINI,Color:Azul`

## Ejemplo de filas esperadas

```csv
External ID,Name,Product Type,Internal Reference,Barcode,Sales Price,Cost,Weight,Sales Description,Product Values
adams_17601_155_s1,Camisa Blanca 17601,Goods,17601-15.5-S1,BARCODE_CONTIFICO,59.99,20,,,"Talla:15.5,Manga de Camisa:S1 - 32/33,Marca:BRUNO CASSINI,Color:Blanco"
adams_17601_155_s2,Camisa Blanca 17601,Goods,17601-15.5-S2,BARCODE_CONTIFICO,59.99,20,,,"Talla:15.5,Manga de Camisa:S2 - 34/35,Marca:BRUNO CASSINI,Color:Blanco"
adams_210001_46,Terno 210001,Goods,210001/46,BARCODE_CONTIFICO,199.99,80,,,"Talla:46,Marca:BRUNO CASSINI,Color:Azul"
```

## Output adicional recomendado

Además del CSV de productos, generar:

### `odoo_initial_stock.csv`

Columnas sugeridas:

- sku
- ubicacion
- cantidad
- costo_unitario

Ubicaciones Odoo:
- `BPU/Existencias`
- `TUR/Existencias`
- `BAT/Existencias`

### `migration_errors.csv`

Columnas sugeridas:

- sku
- nombre
- problema
- raw_data

Registrar ahí productos cuyo SKU no se pueda interpretar, productos sin barcode, productos sin categoría o productos con stock negativo/inconsistente.

## Categorías Odoo

Mapear productos a estas categorías cuando aplique:

- `Ropa / Ternos`
- `Ropa / Camisas`
- `Ropa / Pantalones`
- `Ropa / Levas y Blazers`
- `Ropa / Zapatos`
- `Ropa / Accesorios`
- `Servicios`

## Instrucción para implementación

Primero revisar el código existente de conexión a Contífico en este proyecto.
Luego crear un módulo/sección separada, por ejemplo:

`odoo_migration`

Entregables:
1. función para extraer productos desde Contífico;
2. función para extraer stock por bodega desde Contífico;
3. parser de SKU ADAMS;
4. mapper a columnas Odoo;
5. exportador CSV;
6. reporte de errores;
7. vista previa tabular antes de descargar.

No importar directo a Odoo todavía.
