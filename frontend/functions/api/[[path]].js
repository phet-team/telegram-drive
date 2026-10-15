/**
 * Cloudflare Pages Function: /api/* Reverse Proxy
 * Proxies API requests to the VPS backend via Cloudflare Tunnel.
 * Configure BACKEND_URL in Cloudflare Pages Environment Variables (e.g. https://api-drive.yourdomain.com)
 */
export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  const backendBase = env.BACKEND_URL;
  if (!backendBase) {
    return new Response(
      JSON.stringify({
        error: 'BACKEND_URL is not configured in Cloudflare Pages settings.',
        hint: 'Add BACKEND_URL (e.g. https://tunnel-hostname.com) in Cloudflare Pages > Settings > Environment Variables.'
      }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }

  const targetUrl = new URL(url.pathname + url.search, backendBase);

  const headers = new Headers(request.headers);
  headers.set('X-Forwarded-Host', url.host);

  try {
    const response = await fetch(targetUrl.toString(), {
      method: request.method,
      headers: headers,
      body: request.body,
      redirect: 'manual',
    });

    return response;
  } catch (err) {
    return new Response(
      JSON.stringify({ error: `Backend proxy error: ${err.message}` }),
      { status: 502, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
