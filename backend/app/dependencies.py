from fastapi import Depends, HTTPException, status

from . import auth, models
from .config import get_settings
from .contifico import ContificoClient, ContificoConfigurationError


async def get_current_active_user(
    current_user: models.User = Depends(auth.get_current_user),
) -> models.User:
    """Return the authenticated user (placeholder for future checks)."""

    return current_user


def admin_required():
    return auth.require_roles(models.UserRole.ADMIN)


def staff_required():
    return auth.require_roles(models.UserRole.ADMIN, models.UserRole.VENDEDOR, models.UserRole.SASTRE)


def vendor_or_admin_required():
    return auth.require_roles(models.UserRole.ADMIN, models.UserRole.VENDEDOR)


def tailor_or_admin_required():
    return auth.require_roles(models.UserRole.ADMIN, models.UserRole.SASTRE)


def get_contifico_client() -> ContificoClient:
    """Crea una instancia del cliente de Contífico usando la configuración actual."""

    settings = get_settings()
    if not settings.contifico_api_key or not settings.contifico_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "La integración con Contífico no está configurada. "
                "Define CONTIFICO_API_KEY y CONTIFICO_API_TOKEN en el entorno."
            ),
        )
    try:
        return ContificoClient(
            settings.contifico_api_key,
            settings.contifico_api_token,
            base_url=settings.contifico_api_base_url,
            products_base_url=settings.contifico_products_api_base_url,
            timeout=settings.contifico_timeout_seconds,
            invoice_cache_path=settings.contifico_invoice_cache_path,
            invoice_catalog_page_size=settings.contifico_invoice_catalog_page_size,
            invoice_catalog_max_pages=settings.contifico_invoice_catalog_max_pages,
            invoice_catalog_max_records=settings.contifico_invoice_catalog_max_records,
            invoice_catalog_stop_on_first_match=(
                settings.contifico_invoice_catalog_stop_on_first_match
            ),
        )
    except ContificoConfigurationError as exc:  # pragma: no cover - validación defensiva
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
