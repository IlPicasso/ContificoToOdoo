# Portal de Sastrería

Aplicación completa para gestionar y consultar órdenes de un taller de sastrería. El proyecto incluye un backend basado en FastAPI con autenticación JWT y un frontend ligero en HTML/JavaScript para clientes y personal interno.

## Requisitos

### Backend
- Python 3.10+
- Entorno virtual recomendado

### Frontend
- Cualquier servidor web estático (por ejemplo `python -m http.server`)

## Puesta en marcha

### 1. Preparar el backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

Define la clave secreta JWT en un archivo `.env` dentro de la carpeta `backend` (o como
variable de entorno) antes de iniciar la API:

```bash
cat <<'EOF' > .env
SECRET_KEY="pon-aqui-una-clave-de-al-menos-32-caracteres"
EOF
# También puedes exportarla directamente:
export SECRET_KEY="pon-aqui-una-clave-de-al-menos-32-caracteres"
```

La aplicación fallará con un mensaje descriptivo si `SECRET_KEY` no está definida o es
demasiado corta.

Crear el primer usuario administrador:

```bash
python create_admin.py --username admin --password cambialo --full-name "Administrador"
```

Si necesitas crear un usuario inicial con otro rol, añade la opción `--role` con uno de
los valores disponibles (`admin`, `sales`, `tailor`). El valor predeterminado es
`admin`.

Poblar la base de datos con información de ejemplo (opcional):

```bash
python seed_database.py --reset --yes --users 6 --customers 20 --orders 25
```

Argumentos útiles del comando:

- `--reset`: vacía las tablas antes de insertar los datos ficticios (pide confirmación a menos que se utilice `--yes`).
- `--users`, `--customers`, `--orders`: controlan cuántos usuarios, clientes y órdenes se generan (valores predeterminados: 5, 15 y 20 respectivamente).
- `--yes`: omite la confirmación interactiva para el borrado de datos.

Al finalizar, se mostrará un resumen con los registros creados y las credenciales generadas para los nuevos usuarios.

Iniciar la API:

```bash
python -m app.main
```

Por defecto el servidor escucha en `127.0.0.1:8000`. Para exponerlo en otro host o
puerto (por ejemplo al desplegar en un servidor), define las variables de entorno
`API_HOST`, `API_PORT` y opcionalmente `API_RELOAD` en tu `.env` o antes de ejecutar
el comando. Ejemplo para escuchar en todas las interfaces:

```bash
export API_HOST=0.0.0.0
export API_PORT=8000
python -m app.main
```

La documentación interactiva estará disponible en `http://<host>:<puerto>/docs`.

#### Integración con Contifico

El proyecto incluye un cliente HTTP para la API de Contifico descrita en
https://contifico.github.io/. Configura tus credenciales en el archivo `.env` del
backend (o como variables de entorno) para poder consumir los endpoints oficiales:

```bash
cat <<'EOF' >> .env
CONTIFICO_BASE_URL="https://api.contifico.com/sistema/api/v1"
CONTIFICO_TOKEN="tu-api-key-entregada-por-contifico"
CONTIFICO_TIMEOUT_SECONDS=30
CONTIFICO_RATE_LIMIT_PER_MINUTE=50
CONTIFICO_MAX_RETRIES=3
CONTIFICO_RETRY_BACKOFF_SECONDS=2
EOF
```

El token se envía en el encabezado `Authorization` tal como exige la documentación
de Contifico. Puedes utilizar el helper `ContificoClient` para crear y actualizar
facturas o consultar clientes por identificación:

```python
from app.integrations import ContificoClient
from app.config import get_settings

settings = get_settings()

with ContificoClient(
    base_url=settings.contifico_base_url,
    token=settings.contifico_token,
) as contifico:
    factura = contifico.create_invoice({
        "tipo_documento": "FAC",
        "fecha_emision": "01/01/2025",
        "cliente": {"cedula": "0912345678", "razon_social": "Juan Pérez"},
        "detalles": [
            {
                "producto_id": "COD-PROD",
                "cantidad": 1,
                "precio": 100,
                "porcentaje_iva": 12,
            }
        ],
        "total": 112,
    })

    # Actualiza la factura agregando el identificador devuelto por Contifico.
    contifico.update_invoice(factura["id"], {"descripcion": "Pedido actualizado"})

    posibles_clientes = contifico.get_customer_by_document("0912345678")
```

Cada helper emplea las rutas oficiales (`documento/` y `persona/`) y maneja errores
transitorios (por ejemplo límites de tasa o respuestas 5xx) para que puedas decidir
si debes reintentar la operación o informar al usuario.

### 2. Preparar el frontend

El frontend es una SPA ligera sin dependencias externas. Desde la carpeta `frontend` ejecuta:

```bash
python -m http.server 5173
```

Luego visita `http://localhost:5173` en tu navegador. Asegúrate de que el backend esté funcionando en `http://localhost:8000`.

## Roles disponibles

- **Administrador**: crear usuarios, gestionar clientes y órdenes, consultar la bitácora y eliminar registros.
- **Vendedor**: crear clientes, registrar nuevas órdenes y actualizar sus datos.
- **Sastre**: consultar clientes y órdenes, actualizar los arreglos y estados (sin crear órdenes).

## Funcionalidades principales

- Consulta pública del estado de una orden por número de orden **o** cédula del cliente.
- Catálogo reutilizable de clientes con teléfono y conjuntos de medidas guardadas.
- Gestión interna de órdenes: creación (según rol), actualización de estado, notas y asignación de sastre.
- Aplicación rápida de las medidas guardadas del cliente al generar una orden.
- Bitácora de auditoría inmutable accesible para administradores.
- Gestión de usuarios con control de permisos (Administrador, Vendedor, Sastre).

## Estructura del proyecto

```
backend/       # API FastAPI + SQLAlchemy + SQLite
frontend/      # Portal HTML/JS/CSS
```

## Variables útiles

Si necesitas cambiar la URL del backend para el frontend, define `API_BASE_URL` antes de cargar `app.js`:

```html
<script>
  window.API_BASE_URL = 'http://tu-servidor:8000';
</script>
<script src="app.js"></script>
```

## Comandos recomendados

| Acción | Comando |
|--------|---------|
| Ejecutar pruebas manuales | `uvicorn app.main:app --reload` |
| Servir frontend | `python -m http.server 5173` |

¡Listo! Ya puedes gestionar las órdenes de tu sastrería y ofrecer a tus clientes un portal de consulta.
