import { createHmac, randomUUID, timingSafeEqual } from "node:crypto";

const publicHost = "app.jeeb.fds-1.com";
const descriptorPath = "/internal/ops/staging/realtime-probe-descriptor";
const mintKey = process.env.JEEB_STAGING_WSS_PROBE_MINT_KEY ?? "";

if (Buffer.byteLength(mintKey, "utf8") < 32) {
  throw new Error("JEEB_STAGING_WSS_PROBE_MINT_KEY must contain at least 32 bytes");
}

const nonce = randomUUID();
const timestamp = Math.floor(Date.now() / 1000).toString();
const canonical = `v1\nPOST\n${descriptorPath}\n${timestamp}\n${nonce}`;
const signature = createHmac("sha256", mintKey).update(canonical).digest("hex");
const descriptorResponse = await fetch(`https://${publicHost}${descriptorPath}`, {
  method: "POST",
  headers: {
    accept: "application/json",
    "x-jeeb-staging-probe-timestamp": timestamp,
    "x-jeeb-staging-probe-nonce": nonce,
    "x-jeeb-staging-probe-signature": signature,
  },
  redirect: "manual",
  signal: AbortSignal.timeout(10_000),
});

if (descriptorResponse.status !== 200) {
  throw new Error(`probe descriptor mint returned HTTP ${descriptorResponse.status}`);
}
if (!(descriptorResponse.headers.get("content-type") ?? "").toLowerCase().startsWith("application/json")) {
  throw new Error("probe descriptor mint did not return JSON");
}

const descriptor = await descriptorResponse.json();
const conversationId = `edge-probe-${nonce}`;
const expectedTopic = `jeeb:chat:${conversationId}`;
for (const field of ["socketUrl", "topic", "ticket", "token", "expiresAt"]) {
  if (typeof descriptor[field] !== "string" || descriptor[field].length === 0) {
    throw new Error(`probe descriptor is missing ${field}`);
  }
}
if (descriptor.conversationId !== conversationId || descriptor.topic !== expectedTopic) {
  throw new Error("probe descriptor is not bound to the run nonce and exact chat topic");
}
if (descriptor.roleInConvo !== "client") {
  throw new Error("probe descriptor must use the non-privileged client role");
}

const expiryMs = Date.parse(descriptor.expiresAt);
const remainingMs = expiryMs - Date.now();
if (!Number.isFinite(expiryMs) || remainingMs < 30_000 || remainingMs > 900_000) {
  throw new Error("probe descriptor expiry is outside the 30-900 second safety window");
}

const socketUrl = new URL(descriptor.socketUrl);
if (
  socketUrl.protocol !== "wss:" ||
  socketUrl.hostname !== publicHost ||
  socketUrl.port !== "" ||
  socketUrl.pathname !== "/socket/websocket" ||
  socketUrl.username !== "" ||
  socketUrl.password !== "" ||
  socketUrl.search !== "" ||
  socketUrl.hash !== ""
) {
  throw new Error("probe descriptor socketUrl is not the exact public WSS endpoint");
}
socketUrl.searchParams.set("vsn", "2.0.0");
socketUrl.searchParams.set("token", descriptor.token);

function waitForOpen(socket, timeoutMs = 10_000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("WSS 101 upgrade timed out")), timeoutMs);
    socket.addEventListener("open", () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
    socket.addEventListener("error", () => {
      clearTimeout(timer);
      reject(new Error("authorized WSS request did not receive a 101 upgrade"));
    }, { once: true });
  });
}

function waitForPhoenixReply(socket, expectedRef, timeoutMs = 8_000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error(`Phoenix reply ${expectedRef} timed out`)),
      timeoutMs,
    );
    const onMessage = (event) => {
      let frame;
      try {
        frame = JSON.parse(String(event.data));
      } catch {
        return;
      }
      if (
        Array.isArray(frame) &&
        frame.length === 5 &&
        frame[1] === expectedRef &&
        frame[3] === "phx_reply"
      ) {
        clearTimeout(timer);
        socket.removeEventListener("message", onMessage);
        resolve(frame[4]);
      }
    };
    socket.addEventListener("message", onMessage);
  });
}

function sendPhoenix(socket, joinRef, ref, topic, event, payload) {
  socket.send(JSON.stringify([joinRef, ref, topic, event, payload]));
}

const socket = new WebSocket(socketUrl);
try {
  await waitForOpen(socket);

  const heartbeatRef = "edge-heartbeat-1";
  const heartbeatReply = waitForPhoenixReply(socket, heartbeatRef);
  sendPhoenix(socket, null, heartbeatRef, "phoenix", "heartbeat", {});
  const heartbeatPayload = await heartbeatReply;
  if (heartbeatPayload?.status !== "ok") {
    throw new Error("Phoenix heartbeat did not return status=ok");
  }

  const ticketParts = descriptor.ticket.split(".");
  if (ticketParts.length !== 3 || ticketParts[2].length < 8) {
    throw new Error("probe membership ticket is not a signed three-part token");
  }
  ticketParts[2] = `${ticketParts[2][0] === "A" ? "B" : "A"}${ticketParts[2].slice(1)}`;
  const forgedTicket = ticketParts.join(".");
  const nearMissRef = "edge-near-miss-1";
  const nearMissReply = waitForPhoenixReply(socket, nearMissRef);
  sendPhoenix(socket, nearMissRef, nearMissRef, descriptor.topic, "phx_join", {
    ticket: forgedTicket,
  });
  const nearMissPayload = await nearMissReply;
  const nearMissReason = nearMissPayload?.response?.reason;
  const expectedReason = Buffer.from("not_in_membership", "utf8");
  const actualReason = Buffer.from(String(nearMissReason ?? ""), "utf8");
  if (
    nearMissPayload?.status !== "error" ||
    actualReason.length !== expectedReason.length ||
    !timingSafeEqual(actualReason, expectedReason)
  ) {
    throw new Error("forged membership-ticket near miss was not rejected");
  }

  const joinRef = "edge-join-1";
  const joinReply = waitForPhoenixReply(socket, joinRef);
  sendPhoenix(socket, joinRef, joinRef, descriptor.topic, "phx_join", {
    ticket: descriptor.ticket,
  });
  const joinPayload = await joinReply;
  if (joinPayload?.status !== "ok") {
    throw new Error("authorized exact-topic Phoenix join did not return status=ok");
  }

  console.log("authorized_wss_upgrade=101 heartbeat=ok exact_topic_join=ok forged_ticket=denied");
} finally {
  socket.close(1000, "probe complete");
}
