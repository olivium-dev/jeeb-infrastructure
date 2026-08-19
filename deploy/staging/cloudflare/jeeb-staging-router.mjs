const ORIGINS = Object.freeze({
  "app.jeeb.fds-1.com": "jeeb-app-origin.fds-1.com",
  "cms.jeeb.fds-1.com": "jeeb-cms-origin.fds-1.com",
});

export default {
  async fetch(request, env) {
    const upstream = new URL(request.url);
    const publicHostname = upstream.hostname.toLowerCase();
    const originHostname = ORIGINS[publicHostname];

    if (!originHostname) {
      return new Response("Unknown Jeeb staging host\n", {
        status: 421,
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }

    upstream.hostname = originHostname;

    const headers = new Headers(request.headers);
    headers.set("x-jeeb-origin-key", env.ORIGIN_KEY);
    headers.set("x-forwarded-host", publicHostname);
    headers.set("x-forwarded-proto", "https");

    const init = {
      method: request.method,
      headers,
      redirect: "manual",
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    return fetch(new Request(upstream, init));
  },
};
