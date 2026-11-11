from storage_engine import alerts


class RememberPublicHostMiddleware:
    """Remembers the origin of the latest request so storage alerts can link to the settings page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # get_host() validates against ALLOWED_HOSTS; a bad Host never reaches this far.
        alerts.remember_host(f"{request.scheme}://{request.get_host()}")
        return self.get_response(request)
