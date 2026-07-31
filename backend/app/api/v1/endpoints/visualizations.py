"""Visualization endpoints (frontend-aligned)."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from app.dependencies.rbac import RequireUser
from app.dependencies.services import DashboardServiceDep
from app.schemas.dashboard import DistributorTotal, FilterOptions, KpiItem, ProductQty

router = APIRouter(prefix="/visualizations", tags=["Visualizations"])


@router.get("/products", response_model=List[ProductQty], summary="Product quantities")
def get_product_quantities(
    service: DashboardServiceDep,
    _: RequireUser,
    period: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    distributor: Optional[str] = Query(None),
) -> List[ProductQty]:
    """GET /api/visualizations/products."""
    return service.product_quantities(period=period, product=product, distributor=distributor)


@router.get("/distributors", response_model=List[DistributorTotal], summary="Distributor totals")
def get_distributor_totals(
    service: DashboardServiceDep,
    _: RequireUser,
    period: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    distributor: Optional[str] = Query(None),
) -> List[DistributorTotal]:
    """GET /api/visualizations/distributors."""
    return service.distributor_totals(period=period, product=product, distributor=distributor)


@router.get("/product-mix", response_model=List[Dict[str, Any]], summary="Product mix")
def get_product_mix(
    service: DashboardServiceDep,
    _: RequireUser,
    period: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    distributor: Optional[str] = Query(None),
    top_n: int = Query(7, ge=1, le=50),
) -> List[Dict[str, Any]]:
    """GET /api/visualizations/product-mix."""
    return service.product_mix(
        period=period, product=product, distributor=distributor, top_n=top_n
    )


@router.get("/product-bar", response_model=List[Dict[str, Any]], summary="Product bar data")
def get_product_bar(
    service: DashboardServiceDep,
    _: RequireUser,
    period: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    distributor: Optional[str] = Query(None),
    top_n: int = Query(10, ge=1, le=50),
) -> List[Dict[str, Any]]:
    """GET /api/visualizations/product-bar — Top N + Others."""
    return service.product_bar(
        period=period, product=product, distributor=distributor, top_n=top_n
    )


@router.get(
    "/dist-product-mix",
    response_model=List[Dict[str, Any]],
    summary="Distributor product mix",
)
def get_dist_product_mix(
    service: DashboardServiceDep,
    _: RequireUser,
    period: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    distributor: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    """GET /api/visualizations/dist-product-mix."""
    return service.dist_product_mix(period=period, product=product, distributor=distributor)


@router.get(
    "/top-distributors",
    response_model=List[Dict[str, Any]],
    summary="Top distributors",
)
def get_top_distributors(
    service: DashboardServiceDep,
    _: RequireUser,
    period: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    distributor: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
) -> List[Dict[str, Any]]:
    """GET /api/visualizations/top-distributors."""
    return service.top_distributors(
        period=period, product=product, distributor=distributor, limit=limit
    )


@router.get(
    "/distributor-contribution",
    response_model=List[Dict[str, Any]],
    summary="Distributor contribution (donut)",
)
def get_distributor_contribution(
    service: DashboardServiceDep,
    _: RequireUser,
    period: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    distributor: Optional[str] = Query(None),
    top_n: int = Query(8, ge=1, le=30),
) -> List[Dict[str, Any]]:
    """GET /api/visualizations/distributor-contribution."""
    return service.distributor_contribution(
        period=period, product=product, distributor=distributor, top_n=top_n
    )


@router.get(
    "/monthly-trend",
    response_model=List[Dict[str, Any]],
    summary="Monthly sales trend",
)
def get_monthly_trend(
    service: DashboardServiceDep,
    _: RequireUser,
    product: Optional[str] = Query(None),
    distributor: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    """GET /api/visualizations/monthly-trend — line chart data."""
    return service.monthly_sales_trend(product=product, distributor=distributor)


@router.get(
    "/distributor-month-heatmap",
    response_model=Dict[str, Any],
    summary="Distributor vs month heatmap",
)
def get_distributor_month_heatmap(
    service: DashboardServiceDep,
    _: RequireUser,
    product: Optional[str] = Query(None),
    distributor: Optional[str] = Query(None),
    distributor_limit: int = Query(15, ge=1, le=40),
) -> Dict[str, Any]:
    """GET /api/visualizations/distributor-month-heatmap."""
    return service.distributor_month_heatmap(
        product=product,
        distributor=distributor,
        distributor_limit=distributor_limit,
    )


@router.get("/products-kpi", response_model=List[KpiItem], summary="Products KPIs")
def get_products_kpi(
    service: DashboardServiceDep,
    _: RequireUser,
    period: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    distributor: Optional[str] = Query(None),
) -> List[KpiItem]:
    """Products tab KPIs."""
    return service.products_kpi(period=period, product=product, distributor=distributor)


@router.get("/distributors-kpi", response_model=List[KpiItem], summary="Distributors KPIs")
def get_distributors_kpi(
    service: DashboardServiceDep,
    _: RequireUser,
    period: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    distributor: Optional[str] = Query(None),
) -> List[KpiItem]:
    """Distributors tab KPIs."""
    return service.distributors_kpi(period=period, product=product, distributor=distributor)


@router.get(
    "/product-filter-options",
    response_model=FilterOptions,
    summary="Product filter options",
)
def get_product_filter_options(service: DashboardServiceDep, _: RequireUser) -> FilterOptions:
    """Product visualization filter options."""
    return service.product_filter_options()


@router.get(
    "/distributor-filter-options",
    response_model=FilterOptions,
    summary="Distributor filter options",
)
def get_distributor_filter_options(service: DashboardServiceDep, _: RequireUser) -> FilterOptions:
    """Distributor visualization filter options."""
    return service.distributor_filter_options()
