from django.conf import settings


def piwik(request):
    """Exposes PIWIK_SITE_URL to every template, for templates/piwik.html."""
    return {"PIWIK_SITE_URL": settings.PIWIK_SITE_URL}
