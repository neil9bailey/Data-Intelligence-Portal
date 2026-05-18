from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.auth import get_current_user, require_admin
from app.database import get_session
from app.form_utils import validation_error_response
from app.intelligence_packs import (
    apply_intelligence_pack,
    build_discovery_pack,
    get_preconfigured_customer_pack,
    list_preconfigured_customer_packs,
    list_public_sector_templates,
)
from app.route_utils import context, reference_context, templates


router = APIRouter()


@router.get("/intelligence-packs", response_class=HTMLResponse)
def intelligence_packs(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    return templates.TemplateResponse(
        request,
        "intelligence_packs.html",
        context(
            request,
            customer_packs=list_preconfigured_customer_packs(),
            public_sector_templates=list_public_sector_templates(),
            selected_pack=None,
            apply_result=None,
            form_values={},
            **reference_context(session),
        ),
    )


@router.post("/intelligence-packs/preview", response_class=HTMLResponse)
async def preview_intelligence_pack(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    form_values = {key: str(value) for key, value in form.items()}
    try:
        selected_pack = _pack_from_form(form_values)
    except ValueError as exc:
        return validation_error_response([str(exc)], "/intelligence-packs")
    return templates.TemplateResponse(
        request,
        "intelligence_packs.html",
        context(
            request,
            customer_packs=list_preconfigured_customer_packs(),
            public_sector_templates=list_public_sector_templates(),
            selected_pack=selected_pack,
            apply_result=None,
            form_values=form_values,
            **reference_context(session),
        ),
    )


@router.post("/intelligence-packs/apply", response_class=HTMLResponse)
async def apply_intelligence_pack_route(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    form_values = {key: str(value) for key, value in form.items()}
    try:
        selected_pack = _pack_from_form(form_values)
    except ValueError as exc:
        return validation_error_response([str(exc)], "/intelligence-packs")
    result = apply_intelligence_pack(session, selected_pack, actor=get_current_user(request).username)
    return templates.TemplateResponse(
        request,
        "intelligence_packs.html",
        context(
            request,
            customer_packs=list_preconfigured_customer_packs(),
            public_sector_templates=list_public_sector_templates(),
            selected_pack=selected_pack,
            apply_result=result,
            form_values=form_values,
            **reference_context(session),
        ),
    )


def _pack_from_form(form_values: dict[str, str]) -> dict:
    mode = form_values.get("mode", "built_in")
    if mode == "discover":
        return build_discovery_pack(
            form_values.get("organisation_name", ""),
            form_values.get("template_key", "local_authority"),
            form_values.get("business_unit_name", ""),
        )
    return get_preconfigured_customer_pack(form_values.get("pack_key", "national_highways"))
