"""No real READY without a live, current-session resident model report."""


def ready(health, session, *, simulation=False):
    if not isinstance(health,dict):return False
    if (health.get('sessionId')!=session['sessionId'] or
        health.get('resourceId')!=session['resourceId'] or health.get('modelState')!='ready'):
        return False
    if simulation:return True  # Explicit offline fixtures only; cannot authorize real scope.
    return (health.get('simulation') is False and health.get('modelLoaded') is True and
            health.get('executionMode')=='resident' and
            bool(session.get('hostIdentity')) and health.get('hostIdentity')==session['hostIdentity'])
