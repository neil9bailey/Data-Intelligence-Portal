from app.routes import admin
from app.routes import audit
from app.routes import business_units
from app.routes import client_portal
from app.routes import customers
from app.routes import dashboard
from app.routes import health
from app.routes import intelligence_packs
from app.routes import kra
from app.routes import opportunities
from app.routes import portals
from app.routes import reports
from app.routes import requirements
from app.routes import review
from app.routes import sources


ROUTERS = [
    health.router,
    dashboard.router,
    intelligence_packs.router,
    review.router,
    client_portal.router,
    admin.router,
    business_units.router,
    customers.router,
    sources.router,
    opportunities.router,
    portals.router,
    requirements.router,
    kra.router,
    reports.router,
    audit.router,
]
