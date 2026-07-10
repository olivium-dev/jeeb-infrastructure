# Jeeb Backend — Smoke Test Report

**Date:** 2026-05-20 13:21:29 UTC
**Summary:** 20/58 passed, 31 failed, 7 flagged

## 1. Stack Summary

```
ID             NAME                                 MODE         REPLICAS   IMAGE                                      PORTS
jhf42quqpto6   jeeb_ban-service                     replicated   1/1        jeeb/ban-service:local                     *:10042->3000/tcp
vzszh6892bf0   jeeb_chat-service                    replicated   1/1        jeeb/chat-service:local                    *:10028->8080/tcp
s2j6hdus1dwx   jeeb_compliment-service              replicated   1/1        jeeb/compliment-service:local              *:10036->6070/tcp
t9qlg243eura   jeeb_contract-signing-service        replicated   1/1        jeeb/contract-signing-service:local        *:10011->8000/tcp
9lmwtmf4b9a8   jeeb_delivery-service                replicated   0/1        jeeb/delivery-service:local                *:10005->8080/tcp
s2yet9ajb6s5   jeeb_feedback-service                replicated   1/1        jeeb/feedback-service:local                *:10020->8080/tcp
zmwvgaj5vsf2   jeeb_form-builder-service            replicated   1/1        jeeb/form-builder-service:local            *:10032->8000/tcp
ustlt1qprg71   jeeb_geolocation-service             replicated   1/1        jeeb/geolocation-service:local             *:10006->8000/tcp
vqmiexyvs4xe   jeeb_jeeb-gateway                    replicated   1/1        jeeb/jeeb-gateway:local                    *:10000->8080/tcp
wa64uw9z6bcp   jeeb_matching                        replicated   1/1        jeeb/matching:local                        *:10025->8000/tcp
xsbg73nerl3z   jeeb_mongo                           replicated   1/1        mongo:7                                    
nn9pad3ro9rk   jeeb_notification-service            replicated   1/1        jeeb/notification-service:local            *:10026->8000/tcp
u91eejk9onfz   jeeb_offer-service                   replicated   1/1        jeeb/offer-service:local                   *:10007->4040/tcp
48t4fyzmfc5d   jeeb_postgres                        replicated   1/1        jeeb/postgres-postgis:local                *:15432->5432/tcp
317xkk4vkj14   jeeb_push-notification               replicated   1/1        jeeb/push-notification:local               *:10040->8080/tcp
mujmv33fiw3u   jeeb_realtime-comunication-service   replicated   1/1        jeeb/realtime-comunication-service:local   *:10008->4000/tcp
5wszsokcmluc   jeeb_redis                           replicated   1/1        redis:7-alpine                             *:16379->6379/tcp
y3txs3tsjas8   jeeb_score-taking-service            replicated   1/1        jeeb/score-taking-service:local            *:10009->8080/tcp
k6sb0rrb7dlp   jeeb_unified-payment-gateway         replicated   0/1        jeeb/unified-payment-gateway:local         *:10016->4000/tcp
2t5kpwqgovjf   jeeb_user-management                 replicated   1/1        jeeb/user-management:local                 *:10001->8080/tcp
1640wnexs0kq   jeeb_voice-transcription-service     replicated   1/1        jeeb/voice-transcription-service:local     *:10010->8080/tcp
oybgckad74lb   jeeb_wallet-service                  replicated   1/1        jeeb/wallet-service:local                  *:10014->8080/tcp
```

## 2. Layer A — Per-Service Health

| ID | Service | Port | Health Path | HTTP | Latency | Verdict |
|---|---------|------|-------------|------|---------|---------|
| A-01 | postgres | 15432 | / | 000 | 0s | FLAG |
| A-02 | redis | 16379 | / | 000 | 0s | FLAG |
| A-03 | gateway-live | 10000 | /health/live | 200 | 0.002737s | PASS |
| A-04 | gateway-ready | 10000 | /health/ready | 200 | 0.024495s | PASS |
| A-05 | user-mgmt | 10001 | /api/User/check | 200 | 0.010553s | PASS |
| A-06 | auth | 10003 | /api/Client/SignUpGoogle | 000 | 0s | FLAG |
| A-07 | delivery | 10005 | /health | 000 | 0s | FLAG |
| A-08 | geolocation | 10006 | /health | 200 | 0.002371s | PASS |
| A-09 | offer | 10007 | /health | 200 | 0.002262s | PASS |
| A-10 | realtime | 10008 | / | 404 | 0.002741s | FAIL |
| A-11 | score-take | 10009 | /health | 200 | 0.037686s | PASS |
| A-12 | voice | 10010 | /health/live | 200 | 0.001757s | PASS |
| A-13 | contract | 10011 | /health | 200 | 0.001914s | PASS |
| A-14 | wallet | 10014 | /health | 200 | 0.003719s | PASS |
| A-15 | upg | 10016 | /api/v1/gateways | 000 | 0s | FLAG |
| A-16 | feedback | 10020 | /Review/rating | 400 | 0.033735s | FAIL |
| A-17 | matching | 10025 | /health | 200 | 0.003892s | PASS |
| A-18 | notification | 10026 | /health | 200 | 0.004479s | PASS |
| A-19 | chat | 10028 | /api/health/check | 200 | 0.008661s | PASS |
| A-20 | form-builder | 10032 | /templates | 200 | 0.003334s | PASS |
| A-21 | compliment | 10036 | /health | 200 | 0.006435s | PASS |
| A-22 | push | 10040 | /health | 200 | 0.011425s | PASS |
| A-23 | ban | 10042 | /health | 200 | 0.006206s | PASS |

## 3. Layer B — Gateway Readiness

**HTTP 200**

```json
```

## 4. Layer C — Gateway-Through E2E

| ID | Label | Method | Path | HTTP | Latency | Body (first 200 chars) | Verdict |
|---|-------|--------|------|------|---------|------------------------|---------|
| C-01 | otp-request | POST | /v1/auth/otp/request | 500 | 0.009315s | `System.InvalidOperationException: Unable to resolve service for type 'JeebGateway.Auth.OtpSignIn.IServiceOtpClient' whil` | FAIL |
| C-02 | otp-verify | POST | /v1/auth/otp/verify | 500 | 0.026334s | `System.InvalidOperationException: Unable to resolve service for type 'JeebGateway.Auth.OtpSignIn.IServiceOtpClient' whil` | FAIL |
| C-03 | legacy-token | POST | /auth/tokens | 200 | 0.011407s | `{"accessToken":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzbW9rZS11c2VyIiwianRpIjoiNjEyNzA4OTUtY2I5MC00MGRiLTkwY2Y` | PASS |
| C-04 | role-switch | POST | /v1/users/me/role/switch | 401 | 0.004160s | `{"type":"https://jeeb.dev/errors/unauthenticated","title":"unauthenticated","status":401,"detail":"Request must carry a ` | FAIL |
| C-05 | list-tiers | GET | /tiers | 500 | 0.010406s | `System.InvalidOperationException: An invalid request URI was provided. Either the request URI must be an absolute URI or` | FAIL |
| C-06 | create-request | POST | /requests | 401 | 0.003214s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-a813446a5` | FAIL |
| C-07 | run-matching | POST | /matching/run | 401 | 0.004438s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-2833097bb` | FAIL |
| C-08 | submit-offer | POST | /requests/smoke-req-id/offers | 401 | 0.004436s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-f1389a95a` | FAIL |
| C-09 | accept-offer | POST | /offers/smoke-offer-id/accept | 401 | 0.003756s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-dd14db92f` | FAIL |
| C-10 | gps-update | POST | /location/update | 401 | 0.003933s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-b17a0afa4` | FAIL |
| C-11 | status-picked | PATCH | /deliveries/smoke-req-id/status | 401 | 0.014708s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-1783f23bc` | FAIL |
| C-12 | cash-settle | POST | /deliveries/smoke-req-id/settle | 401 | 0.005250s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-2abe67a87` | FAIL |
| C-13 | wallet-balance | GET | /api/wallet/balance | 401 | 0.004935s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-182c56136` | FAIL |
| C-14 | earnings-summary | GET | /api/earnings/summary | 401 | 0.002794s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-156b6186e` | FAIL |
| C-15 | earnings-pdf | GET | /api/earnings/statement?period=2026-W20 | 401 | 0.004064s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-246e75d22` | FAIL |
| C-16 | blind-rate | POST | /api/deliveries/smoke-req-id/rate | 401 | 0.003874s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-078ad7953` | FAIL |
| C-17 | chat-msg | POST | /chat/messages | 401 | 0.012186s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-45b917a07` | FAIL |
| C-18 | push-device | POST | /push/devices | 401 | 0.006207s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-cfc15cf10` | FAIL |
| C-19 | cancel-delivery | POST | /deliveries/smoke-req-id/cancel | 401 | 0.004266s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-a9c1c2559` | FAIL |
| C-20a | file-dispute | POST | /deliveries/smoke-req-id/dispute | 401 | 0.019665s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-97e63aff2` | FAIL |
| C-20b | resolve-dispute | PUT | /admin/disputes/smoke-dispute-id/resolve | 401 | 0.012347s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-3002a1fc2` | FAIL |
| C-21 | prohibited-scan | POST | /prohibited-items/scan | 401 | 0.042134s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-cf60c8c78` | FAIL |
| C-22 | kyc-submit | POST | /kyc/submit | 401 | 0.009650s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-ab7f8b943` | FAIL |
| C-23 | availability | PATCH | /jeebers/me/availability | 401 | 0.003756s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-9195385d8` | FAIL |
| C-24 | transcribe | POST | /transcribe | 500 | 0.116857s | `System.Net.Http.HttpRequestException: Response status code does not indicate success: 401 (Unauthorized).    at System.N` | FAIL |
| C-25 | admin-zones | GET | /admin/zones/online-jeebers | 401 | 0.003862s | `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-778bfea3d` | FAIL |

## 5. Layer D — Direct Service Curls

| ID | Label | Method | URL | HTTP | Latency | Verdict |
|---|-------|--------|-----|------|---------|---------|
| D-01 | compliment-create | POST | http://localhost:10036/api/v1/compliments/ | 422 | 0.006191s | FAIL |
| D-02 | contract-create | POST | http://localhost:10011/v1/contracts | 422 | 0.002836s | FAIL |
| D-03 | feedback-rating | GET | http://localhost:10020/Review/rating?userId=u1 | 400 | 0.003046s | FAIL |
| D-04 | form-components | GET | http://localhost:10032/components | 200 | 0.003025s | PASS |
| D-05 | upg-gateways | GET | http://localhost:10016/api/v1/gateways | 000 | 0s | FLAG |
| D-06 | upg-payment | POST | http://localhost:10016/api/v1/payments | 000 | 0s | FLAG |
| D-07 | ban-status | GET | http://localhost:10042/api/v1/ban/smoke-user/status | 400 | 0.016233s | FAIL |
| D-08 | offer-ready | GET | http://localhost:10007/health/ready | 200 | 0.003731s | PASS |

## 6. Failure Summary

- **A-10 (realtime):** `GET http://localhost:10008/` → HTTP 404
  ```
{"error":"not_found","message":"Resource not found"}  ```
- **A-16 (feedback):** `GET http://localhost:10020/Review/rating` → HTTP 400
  ```
{"success":false,"error":"Validation Failed","reason":"Tag parameter is required.","errorCode":"VALIDATION_ERROR","timestamp":"2026-05-20T13:21:24.7449447Z","details":{"parameter":"tag","message":"Tag cannot be null or empty."}}  ```
- **C-01 (otp-request):** `POST http://localhost:10000/v1/auth/otp/request` → HTTP 500
  ```
System.InvalidOperationException: Unable to resolve service for type 'JeebGateway.Auth.OtpSignIn.IServiceOtpClient' while attempting to activate 'JeebGateway.Auth.OtpSignIn.AuthOtpController'.
   at Microsoft.Extensions.DependencyInjection.ActivatorUtilities.ThrowHelperUnableToResolveService(Type type, Type requiredBy)
   at lambda_method486(Closure, IServiceProvider, Object[])
   at Microsoft.AspNetCore.Mvc.Controllers.ControllerFactoryProvider.<>c__DisplayClass6_0.<CreateControllerFactory>g__C  ```
- **C-02 (otp-verify):** `POST http://localhost:10000/v1/auth/otp/verify` → HTTP 500
  ```
System.InvalidOperationException: Unable to resolve service for type 'JeebGateway.Auth.OtpSignIn.IServiceOtpClient' while attempting to activate 'JeebGateway.Auth.OtpSignIn.AuthOtpController'.
   at Microsoft.Extensions.DependencyInjection.ActivatorUtilities.ThrowHelperUnableToResolveService(Type type, Type requiredBy)
   at lambda_method494(Closure, IServiceProvider, Object[])
   at Microsoft.AspNetCore.Mvc.Controllers.ControllerFactoryProvider.<>c__DisplayClass6_0.<CreateControllerFactory>g__C  ```
- **C-04 (role-switch):** `POST http://localhost:10000/v1/users/me/role/switch` → HTTP 401
  ```
{"type":"https://jeeb.dev/errors/unauthenticated","title":"unauthenticated","status":401,"detail":"Request must carry a valid bearer token or X-User-Id header.","instance":"/v1/users/me/role/switch"}  ```
- **C-05 (list-tiers):** `GET http://localhost:10000/tiers` → HTTP 500
  ```
System.InvalidOperationException: An invalid request URI was provided. Either the request URI must be an absolute URI or BaseAddress must be set.
   at System.Net.Http.HttpClient.PrepareRequestMessage(HttpRequestMessage request)
   at System.Net.Http.HttpClient.SendAsync(HttpRequestMessage request, HttpCompletionOption completionOption, CancellationToken cancellationToken)
   at JeebGateway.Services.Clients.DeliveryServiceClient.ListTiersAsync(CancellationToken ct) in /src/src/JeebGateway/Servic  ```
- **C-06 (create-request):** `POST http://localhost:10000/requests` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-a813446a5910f846e9a1084348bdc207-0311ff7d196b80a1-01"}  ```
- **C-07 (run-matching):** `POST http://localhost:10000/matching/run` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-2833097bb75dd853010b311043d1936c-3fcf07dc34214044-01"}  ```
- **C-08 (submit-offer):** `POST http://localhost:10000/requests/smoke-req-id/offers` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-f1389a95a2e894bf88feb277457f5fd6-e0497247dcf27325-01"}  ```
- **C-09 (accept-offer):** `POST http://localhost:10000/offers/smoke-offer-id/accept` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-dd14db92f64d71196c3ca404f11291c8-8962fc247b55313c-01"}  ```
- **C-10 (gps-update):** `POST http://localhost:10000/location/update` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-b17a0afa41b7619d350e29346b6f45d8-9f0e594486f083d6-01"}  ```
- **C-11 (status-picked):** `PATCH http://localhost:10000/deliveries/smoke-req-id/status` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-1783f23bcb43bd936bb00b5c7e485c0a-4185570bd754384d-01"}  ```
- **C-12 (cash-settle):** `POST http://localhost:10000/deliveries/smoke-req-id/settle` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-2abe67a87c890620ead021c6ca610916-4fd2b9936dd56345-01"}  ```
- **C-13 (wallet-balance):** `GET http://localhost:10000/api/wallet/balance` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-182c561367d189ce23561ea992b950bf-d4c5d7c7539716de-01"}  ```
- **C-14 (earnings-summary):** `GET http://localhost:10000/api/earnings/summary` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-156b6186edd63f3ca9a8502ca8c1229a-9700d5b6b6718df9-01"}  ```
- **C-15 (earnings-pdf):** `GET http://localhost:10000/api/earnings/statement?period=2026-W20` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-246e75d22d2ef8294315fb68ef5aa205-89c407ffe1f3814f-01"}  ```
- **C-16 (blind-rate):** `POST http://localhost:10000/api/deliveries/smoke-req-id/rate` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-078ad7953439423fb883c4c2c72777c3-ef485100d8f02d21-01"}  ```
- **C-17 (chat-msg):** `POST http://localhost:10000/chat/messages` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-45b917a07d8c266d6f326adb76ffae36-e9830460f0b890ad-01"}  ```
- **C-18 (push-device):** `POST http://localhost:10000/push/devices` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-cfc15cf10f357c23e110739c0bcbdb55-dd0a841ea9afa2a6-01"}  ```
- **C-19 (cancel-delivery):** `POST http://localhost:10000/deliveries/smoke-req-id/cancel` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-a9c1c25598c7fa15cd7c377df8a5d231-78608766f0612956-01"}  ```
- **C-20a (file-dispute):** `POST http://localhost:10000/deliveries/smoke-req-id/dispute` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-97e63aff22c351f397b04f374690ed59-37e55d909f02f151-01"}  ```
- **C-20b (resolve-dispute):** `PUT http://localhost:10000/admin/disputes/smoke-dispute-id/resolve` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-3002a1fc20c9940a6e8e56f0379ef21f-3a156fafe1b7ce93-01"}  ```
- **C-21 (prohibited-scan):** `POST http://localhost:10000/prohibited-items/scan` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-cf60c8c786f592c19484ba7cb39e6d76-11cec40f24786e1c-01"}  ```
- **C-22 (kyc-submit):** `POST http://localhost:10000/kyc/submit` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-ab7f8b9434120dec74311715c7bb5b43-69f1be561543da68-01"}  ```
- **C-23 (availability):** `PATCH http://localhost:10000/jeebers/me/availability` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-9195385d850bcaad5d8abbc7a17f3fec-be375f494e36284d-01"}  ```
- **C-24 (transcribe):** `POST http://localhost:10000/transcribe` → HTTP 500
  ```
System.Net.Http.HttpRequestException: Response status code does not indicate success: 401 (Unauthorized).
   at System.Net.Http.HttpResponseMessage.EnsureSuccessStatusCode()
   at JeebGateway.Whisper.WhisperClient.TranscribeAsync(WhisperAudio audio, CancellationToken ct) in /src/src/JeebGateway/Whisper/WhisperClient.cs:line 65
   at JeebGateway.Whisper.ResilientTranscriptionService.TranscribeAsync(WhisperAudio audio, CancellationToken ct) in /src/src/JeebGateway/Whisper/ResilientTranscriptionSer  ```
- **C-25 (admin-zones):** `GET http://localhost:10000/admin/zones/online-jeebers` → HTTP 401
  ```
{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.2","title":"Unauthorized","status":401,"traceId":"00-778bfea3d212705c010ab89adbc6d2c2-943c65f693797729-01"}  ```
- **D-01 (compliment-create):** `POST http://localhost:10036/api/v1/compliments/` → HTTP 422
  ```
{"detail":[{"type":"missing","loc":["body","partner_id_1"],"msg":"Field required","input":{"fromUserId":"u1","toUserId":"u2","kind":"polite"}},{"type":"missing","loc":["body","partner_id_2"],"msg":"Field required","input":{"fromUserId":"u1","toUserId":"u2","kind":"polite"}},{"type":"missing","loc":["body","message"],"msg":"Field required","input":{"fromUserId":"u1","toUserId":"u2","kind":"polite"}}]}  ```
- **D-02 (contract-create):** `POST http://localhost:10011/v1/contracts` → HTTP 422
  ```
{"detail":[{"type":"missing","loc":["body","template_id"],"msg":"Field required","input":{"templateId":"jeeber-tos-v1","userId":"u1"},"url":"https://errors.pydantic.dev/2.5/v/missing"},{"type":"missing","loc":["body","parties"],"msg":"Field required","input":{"templateId":"jeeber-tos-v1","userId":"u1"},"url":"https://errors.pydantic.dev/2.5/v/missing"},{"type":"missing","loc":["body","actor"],"msg":"Field required","input":{"templateId":"jeeber-tos-v1","userId":"u1"},"url":"https://errors.pydant  ```
- **D-03 (feedback-rating):** `GET http://localhost:10020/Review/rating?userId=u1` → HTTP 400
  ```
{"success":false,"error":"Validation Failed","reason":"Tag parameter is required.","errorCode":"VALIDATION_ERROR","timestamp":"2026-05-20T13:21:29.311413Z","details":{"parameter":"tag","message":"Tag cannot be null or empty."}}  ```
- **D-07 (ban-status):** `GET http://localhost:10042/api/v1/ban/smoke-user/status` → HTTP 400
  ```
{"error":"BAD_REQUEST","message":"Invalid UUID format: smoke-user"}  ```

## 7. Next Actions

- [ ] Investigate failed services (see failure summary above)
- [ ] Check `docker service logs jeeb_<service>` for crash loops
- [ ] Verify environment variables are correctly injected
- [ ] Review flagged results — may be expected (e.g. Whisper without API key, Postgres/Redis TCP probes)
- [ ] Run Pact/Schemathesis contract tests as follow-up
- [ ] Run load tests with oha/vegeta for perf baselines

## 8. Appendix — Stack State

```
ID                          NAME                                   IMAGE                                                                                    NODE             DESIRED STATE   CURRENT STATE                      ERROR                                          PORTS
u049z3q1jc713k4qoy6uw0z96   jeeb_ban-service.1                     jeeb/ban-service:local                                                                   docker-desktop   Running         Running 16 hours ago                                                              
kvpc1t4dz3y79h1e5643hw85u   jeeb_chat-service.1                    jeeb/chat-service:local                                                                  docker-desktop   Running         Running 16 hours ago                                                              
oyen67tm3pgv2wcuc8p0mufzt   jeeb_compliment-service.1              jeeb/compliment-service:local                                                            docker-desktop   Running         Running 16 hours ago                                                              
0rhhc2e2b1cvdvdu4sak86ymf   jeeb_contract-signing-service.1        jeeb/contract-signing-service:local                                                      docker-desktop   Running         Running 16 hours ago                                                              
cy3hxqu8dx1izkoaakjhpasnm    \_ jeeb_contract-signing-service.1    jeeb/contract-signing-service:local                                                      docker-desktop   Shutdown        Failed 16 hours ago                "task: non-zero exit (3)"                      
xhrjm0lgmaz75znkl0awc4d4r    \_ jeeb_contract-signing-service.1    jeeb/contract-signing-service:local                                                      docker-desktop   Shutdown        Failed 16 hours ago                "task: non-zero exit (3)"                      
f0xdj20uyu8ov3x3v0u8thdx1   jeeb_delivery-service.1                jeeb/delivery-service:local                                                              docker-desktop   Ready           Preparing less than a second ago                                                  
ku48fwv31c6zxp0bsbtp6y0hb    \_ jeeb_delivery-service.1            jeeb/delivery-service:local                                                              docker-desktop   Shutdown        Rejected 4 seconds ago             "No such image: jeeb/delivery-service:local"   
milqom9olhcb22lz8x4b64lx8    \_ jeeb_delivery-service.1            jeeb/delivery-service:local                                                              docker-desktop   Shutdown        Rejected 9 seconds ago             "No such image: jeeb/delivery-service:local"   
xndhpyzhp63riabckp8936kmk    \_ jeeb_delivery-service.1            jeeb/delivery-service:local                                                              docker-desktop   Shutdown        Rejected 14 seconds ago            "No such image: jeeb/delivery-service:local"   
bta752plr0uw9xart8vwc9ctg    \_ jeeb_delivery-service.1            jeeb/delivery-service:local                                                              docker-desktop   Shutdown        Rejected 19 seconds ago            "No such image: jeeb/delivery-service:local"   
gj3u0w8k1xeghidk06hn3eyba   jeeb_feedback-service.1                jeeb/feedback-service:local                                                              docker-desktop   Running         Running 16 hours ago                                                              
z4ozv910yzn4oeuhwa9wf3a7a    \_ jeeb_feedback-service.1            jeeb/feedback-service:local                                                              docker-desktop   Shutdown        Failed 16 hours ago                "task: non-zero exit (133)"                    
wp9rfnyalcxqxyf9tqkou0xtn   jeeb_form-builder-service.1            jeeb/form-builder-service:local                                                          docker-desktop   Running         Running 16 hours ago                                                              
64mgoxz4hiumt8ostz5su1tfv    \_ jeeb_form-builder-service.1        jeeb/form-builder-service:local                                                          docker-desktop   Shutdown        Failed 16 hours ago                "task: non-zero exit (3)"                      
itugnyrayn0moe9f2k4ge4o0a   jeeb_geolocation-service.1             jeeb/geolocation-service:local                                                           docker-desktop   Running         Running 16 hours ago                                                              
mwjitld1ggv72ho8arymaf34a   jeeb_jeeb-gateway.1                    jeeb/jeeb-gateway:local                                                                  docker-desktop   Running         Running 16 hours ago                                                              
repta4l059d70t5ufv0kt6gwu    \_ jeeb_jeeb-gateway.1                jeeb/jeeb-gateway:local                                                                  docker-desktop   Shutdown        Shutdown 16 hours ago                                                             
pvyiyv7qf6zcaatvix63a1cdc    \_ jeeb_jeeb-gateway.1                jeeb/jeeb-gateway:local                                                                  docker-desktop   Shutdown        Shutdown 16 hours ago                                                             
5pig267b0kfmdl3v4lzqs01dy   jeeb_matching.1                        jeeb/matching:local                                                                      docker-desktop   Running         Running 16 hours ago                                                              
27v1eztacexyakl0581v02gbw    \_ jeeb_matching.1                    jeeb/matching:local                                                                      docker-desktop   Shutdown        Failed 16 hours ago                "task: non-zero exit (1)"                      
aturm1ypio1171rxsfowzxlrx   jeeb_mongo.1                           mongo:7@sha256:4b5bf3c2bb7516164f6dcb44acce4fdcb428abfe5771a1128304a0f34ab9ff7c          docker-desktop   Running         Running 16 hours ago                                                              
uuu9meoyz0nime7patgs2k1a6   jeeb_notification-service.1            jeeb/notification-service:local                                                          docker-desktop   Running         Running 16 hours ago                                                              
8bblfgxhvhif6pw6rlaeq3t78   jeeb_offer-service.1                   jeeb/offer-service:local                                                                 docker-desktop   Running         Running 16 hours ago                                                              
uqwnbri5wz4vpbtvvybzxnm88    \_ jeeb_offer-service.1               jeeb/offer-service:local                                                                 docker-desktop   Shutdown        Failed 16 hours ago                "task: non-zero exit (1)"                      
kw4ti4uc0www1i5oq280tck4z   jeeb_postgres.1                        jeeb/postgres-postgis:local                                                              docker-desktop   Running         Running 16 hours ago                                                              
xiofs5x9w1jsu9nd1kp4iqlh9   jeeb_push-notification.1               jeeb/push-notification:local                                                             docker-desktop   Running         Running 16 hours ago                                                              
souv2p9t8znzb9bcqnhg51zu2   jeeb_realtime-comunication-service.1   jeeb/realtime-comunication-service:local                                                 docker-desktop   Running         Running 16 hours ago                                                              
6mpqqyknil13ftv67cegn76zc   jeeb_redis.1                           redis:7-alpine@sha256:6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99   docker-desktop   Running         Running 16 hours ago                                                              
stq66fl2lpk195bii3ciq01nb   jeeb_score-taking-service.1            jeeb/score-taking-service:local                                                          docker-desktop   Running         Running 16 hours ago                                                              
ra0sms19u44xdukp24tbhx01a    \_ jeeb_score-taking-service.1        jeeb/score-taking-service:local                                                          docker-desktop   Shutdown        Failed 16 hours ago                "task: non-zero exit (133)"                    
oo9y5307faku7l4v4p7e8lhl3    \_ jeeb_score-taking-service.1        jeeb/score-taking-service:local                                                          docker-desktop   Shutdown        Failed 16 hours ago                "task: non-zero exit (133)"                    
v058qr0m009q9v839hib52w37   jeeb_unified-payment-gateway.1         jeeb/unified-payment-gateway:local                                                       docker-desktop   Ready           Ready 3 seconds ago                                                               
14ixmuccemidmvzjivno0pk0h    \_ jeeb_unified-payment-gateway.1     jeeb/unified-payment-gateway:local                                                       docker-desktop   Running         Ready 3 seconds ago                                                               
lon5y2ne67u1qlto8r0cq712m    \_ jeeb_unified-payment-gateway.1     jeeb/unified-payment-gateway:local                                                       docker-desktop   Running         Running less than a second ago                                                    
vm4rpzej5j2zlc08951vvfawe    \_ jeeb_unified-payment-gateway.1     jeeb/unified-payment-gateway:local                                                       docker-desktop   Shutdown        Failed 5 seconds ago               "task: non-zero exit (1)"                      
y7ucz3ffn8k3f50vsc87pv91v    \_ jeeb_unified-payment-gateway.1     jeeb/unified-payment-gateway:local                                                       docker-desktop   Shutdown        Failed 5 seconds ago               "task: non-zero exit (1)"                      
xuqc6mas3jnt2qe59a69vs3qd   jeeb_user-management.1                 jeeb/user-management:local                                                               docker-desktop   Running         Running 16 hours ago                                                              
x8nnnhgrj7sx8q41r5m4ik719   jeeb_voice-transcription-service.1     jeeb/voice-transcription-service:local                                                   docker-desktop   Running         Running 16 hours ago                                                              
okr0aikgn9e2b3blnkdjx8n1i   jeeb_wallet-service.1                  jeeb/wallet-service:local                                                                docker-desktop   Running         Running 16 hours ago                                                              
```

### Service Logs (failed services, last 200 lines)

#### jeeb_realtime
```
(no logs available for jeeb_realtime)
```

#### jeeb_feedback
```
(no logs available for jeeb_feedback)
```

#### jeeb_otp-request
```
(no logs available for jeeb_otp-request)
```

#### jeeb_otp-verify
```
(no logs available for jeeb_otp-verify)
```

#### jeeb_role-switch
```
(no logs available for jeeb_role-switch)
```

#### jeeb_list-tiers
```
(no logs available for jeeb_list-tiers)
```

#### jeeb_create-request
```
(no logs available for jeeb_create-request)
```

#### jeeb_run-matching
```
(no logs available for jeeb_run-matching)
```

#### jeeb_submit-offer
```
(no logs available for jeeb_submit-offer)
```

#### jeeb_accept-offer
```
(no logs available for jeeb_accept-offer)
```

#### jeeb_gps-update
```
(no logs available for jeeb_gps-update)
```

#### jeeb_status-picked
```
(no logs available for jeeb_status-picked)
```

#### jeeb_cash-settle
```
(no logs available for jeeb_cash-settle)
```

#### jeeb_wallet-balance
```
(no logs available for jeeb_wallet-balance)
```

#### jeeb_earnings-summary
```
(no logs available for jeeb_earnings-summary)
```

#### jeeb_earnings-pdf
```
(no logs available for jeeb_earnings-pdf)
```

#### jeeb_blind-rate
```
(no logs available for jeeb_blind-rate)
```

#### jeeb_chat-msg
```
(no logs available for jeeb_chat-msg)
```

#### jeeb_push-device
```
(no logs available for jeeb_push-device)
```

#### jeeb_cancel-delivery
```
(no logs available for jeeb_cancel-delivery)
```

#### jeeb_file-dispute
```
(no logs available for jeeb_file-dispute)
```

#### jeeb_resolve-dispute
```
(no logs available for jeeb_resolve-dispute)
```

#### jeeb_prohibited-scan
```
(no logs available for jeeb_prohibited-scan)
```

#### jeeb_kyc-submit
```
(no logs available for jeeb_kyc-submit)
```

#### jeeb_availability
```
(no logs available for jeeb_availability)
```

#### jeeb_transcribe
```
(no logs available for jeeb_transcribe)
```

#### jeeb_admin-zones
```
(no logs available for jeeb_admin-zones)
```

#### jeeb_compliment-create
```
(no logs available for jeeb_compliment-create)
```

#### jeeb_contract-create
```
(no logs available for jeeb_contract-create)
```

#### jeeb_feedback-rating
```
(no logs available for jeeb_feedback-rating)
```

#### jeeb_ban-status
```
(no logs available for jeeb_ban-status)
```

