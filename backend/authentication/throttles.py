from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


def get_client_ip(request):
    cf_ip = request.META.get('HTTP_CF_CONNECTING_IP')
    if cf_ip:
        return cf_ip.strip()
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


class CloudflareAnonRateThrottle(AnonRateThrottle):
    def get_ident(self, request):
        return get_client_ip(request)


class AuthAnonRateThrottle(AnonRateThrottle):
    scope = 'auth'
    rate = '10/min'

    def get_ident(self, request):
        return get_client_ip(request)


class StrictLoginRateThrottle(AnonRateThrottle):
    scope = 'login'
    rate = '5/min'

    def get_ident(self, request):
        return get_client_ip(request)
