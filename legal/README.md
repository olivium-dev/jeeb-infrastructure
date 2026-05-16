# Jeeb — Legal Documents

This directory contains the canonical legal documents that govern use of the
Jeeb platform. Both English (`en/`) and Arabic (`ar/`) versions are maintained
in lock-step; any change to a clause MUST be applied to both locales in the
same pull request.

> **Status:** DRAFT v0.1 — pending review by qualified legal counsel licensed
> in the operating jurisdiction. These drafts establish structure, scope, and
> bilingual parity, but they are NOT a substitute for jurisdiction-specific
> legal advice and MUST be reviewed before publication to end users.

## Documents

| Document            | English                           | Arabic                             |
| ------------------- | --------------------------------- | ---------------------------------- |
| Terms of Service    | [en/terms-of-service.md](./en/terms-of-service.md) | [ar/terms-of-service.md](./ar/terms-of-service.md) |
| Privacy Policy      | [en/privacy-policy.md](./en/privacy-policy.md)     | [ar/privacy-policy.md](./ar/privacy-policy.md)     |
| Prohibited Items    | [en/prohibited-items.md](./en/prohibited-items.md) | [ar/prohibited-items.md](./ar/prohibited-items.md) |

## Roles defined

- **Client** — an end user who requests a delivery, errand, or service through
  the Jeeb mobile app.
- **Jeeber** — an independent contractor who accepts and fulfils Client
  requests through the Jeeber-side of the platform. Jeebers are NOT employees
  of Jeeb and the Terms make this relationship explicit.
- **Jeeb** — the platform operator, which provides the technology that
  connects Clients and Jeebers but is not itself a party to the underlying
  transport, delivery, or service contract between them.

## Versioning

Each document carries a header with `Version`, `Effective date`, and
`Last reviewed` fields. Any material change increments the version, updates
the effective date, and is announced in-app at least 14 days before it takes
effect. Material changes also trigger a re-consent flow for existing users.

## Translation parity

Where the English and Arabic texts diverge, the document specifies which
version is the legally binding one for disputes in the relevant jurisdiction.
Translators MUST flag any clause where literal translation would change
meaning so legal counsel can issue an equivalent (not literal) rendering.

## Change process

1. Open a PR against `main` titled `legal: <document> v<old>→v<new>`.
2. Update BOTH locales in the same PR — CI will reject single-locale changes.
3. Tag `@olivium-dev/legal` and `@olivium-dev/product` as reviewers.
4. Once merged, the Operations team announces the change via the in-app
   notification service and the public changelog.
