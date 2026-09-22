"""
Dashboard refresh (Module F).

Used to be EventBridge firing a Step Functions state machine. It is now a
function the upload route schedules as a background task -- the orchestration
existed to cross a network boundary that no longer exists.
"""
from shared.log import logger

from services.dashboard import generate


def refresh(business_id: str) -> dict:
    """Regenerate a business's dashboard after new data lands, so it is already
    current the next time they open it."""
    dashboard = generate(business_id)
    logger.info("Dashboard refreshed in the background", business_id=business_id,
                kpis=len(dashboard["kpis"]), charts=len(dashboard["charts"]))
    return dashboard
