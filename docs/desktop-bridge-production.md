# VERA Desktop bridge: production architecture proposal

Status: design proposal, not implemented or approved for public distribution.
Prepared September 17, 2026. Start with the
[proof-of-concept plan](desktop-bridge-poc.md).

## Product intent

Users install Desktop once, choose libraries, and link the VERA ChatGPT plugin.
Desktop manages retrieval, models, source previews, credentials, and connection
health. `.vera` files remain ordinary portable local archives, usable through
Desktop and CLI even without a VERA account or relay connection.

The intended privacy promise is: **Your library stays on your computer; requested
excerpts and source previews are shared with ChatGPT.** A relay processes those
payloads in transit. This is not a promise that document content never leaves the
device, that the relay cannot see content, or that ChatGPT retains nothing.

## Why a public relay

OpenAI's current documentation distinguishes private tunnel testing from public
plugin distribution, which requires a publicly reachable HTTPS MCP endpoint.
The proposal is to operate that endpoint while keeping the actual library and
retrieval process local. Revalidate endpoint, authentication, and review rules
before implementation or submission; this architecture is not an approval
guarantee. [OpenAI connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt/)

```text
ChatGPT plugin -- HTTPS MCP + user authorization --> VERA relay
                                                       ^
                                  authenticated outbound device connection
                                                       |
                                               Desktop bridge
                                                       |
                                            approved local libraries
```

The relay exposes MCP and routes authorized requests to a particular enrolled
device. Desktop initiates the network connection so users do not configure router
ports. An outbound TLS WebSocket is a candidate transport; finalize transport
after testing deadlines, cancellation, reconnects, and proxy compatibility.
Use established identity/OAuth libraries rather than creating an auth protocol.

## Responsibilities and data boundaries

| Component | Responsibilities | Persistent data |
| --- | --- | --- |
| Desktop | Library grants, search, embeddings, rendering, local audit display | Archives/indexes, local path mapping, encrypted device credentials |
| Relay | Public MCP, token validation, device routing, quotas, protocol negotiation | Accounts, device identities, grants, revocation state, minimal operational metadata |
| ChatGPT | Tool selection, answer generation, citation UI hosting | Governed by the user's ChatGPT settings and applicable service policies |

Do not store archive uploads, document text, embeddings, preview pages, queries,
or tool-response bodies in the relay database, analytics, durable queues, or
ordinary logs. Use bounded in-memory buffers with request deadlines. Configure
proxy/APM/error reporting and crash handling so payloads are not accidentally
captured. Specify and publish retention for operational metadata separately.
Transport encryption protects each connection; the relay terminates TLS and
therefore can process plaintext. Do not market this as end-to-end encryption.

## Enrollment and authorization

1. Desktop signs the user into a VERA identity service through the system browser,
   using a standard native-app authorization flow with PKCE or supported device
   authorization. Register a distinct device identity and display its name.
2. The user selects local libraries and explicitly enables remote read access.
   Store a grant version locally; opening a folder in Desktop does not grant it.
3. Installing/linking the ChatGPT plugin completes the supported MCP authorization
   flow against VERA. The user chooses an enrolled device and approved libraries.
4. Relay validates token audience, issuer, expiry, scopes, and the user/device/grant
   binding on every request. Device authentication is separate from ChatGPT access
   tokens; never route by a caller-supplied user ID alone.
5. Desktop independently checks the effective local grant for every operation.
   Cloud authorization may narrow access but cannot expand the local grant.

Use short-lived credentials and rotation, keep device secrets in OS-backed
storage, and support revoking a device or integration from either end. Local
Disconnect stops access immediately; server revocation prevents new dispatches,
closes applicable sessions, and discards pending results. Previously delivered
content remains outside that revocation boundary. Reconnect must revalidate grants
and cannot replay work authorized before revocation.

The precise OAuth discovery, registration, and scope contract is an implementation
gate: validate it against current official requirements and the target ChatGPT
client. Do not assume the POC's tunnel credential is production user identity.

## Tool and routing contract

Use opaque library/document identifiers in the public API, with device-local path
resolution. Preserve stable citation references to an archive revision and chunk;
reject stale references rather than showing evidence from a replaced archive.
Update viewer calls and plugin instructions together. Keep legacy path-based
local MCP clients working through their existing interface.

Carry request ID, protocol version, authorized device/grant context, deadline,
tool name, and validated arguments in the internal envelope. Maintain per-user
session isolation. Forward MCP initialization, discovery, resources, tool results,
UI metadata, errors, and cancellation correctly; this is more than proxying tool
JSON. Validate that the source viewer and page navigation survive the full path.
Enforce tool allowlists, page/result/payload limits, and bounded concurrency at
both relay and device. Remote tools do not accept arbitrary file paths, URLs,
shell commands, or runtime configuration.

When a device is asleep or disconnected, return an actionable unavailable error;
do not durably queue document requests. Use bounded deduplication for retry IDs
and discard late responses. Never reroute to another device implicitly. Start
with one selected device per integration; multi-device search is a later feature.

## Desktop operation and reliability

Offer an explicit option to keep the bridge running in the background, with a
tray status indicator, pause/disconnect, and optional launch at login. Explain
that sleeping or offline computers cannot answer. Keep UI lifecycle separate
from the bridge worker so closing a window has the chosen, predictable behavior.

Use signed installers and authenticated updates, protocol compatibility checks,
health checks, bounded reconnect backoff, and resource limits. Roll out by feature
flag and retain a disable switch. Local retrieval must continue working through
relay outages. Define service targets after measuring POC latency and preview
bandwidth; account for network egress, concurrent device connections, identity
operations, and support costs before choosing a business model.

## Delivery stages and release gates

| Stage | Deliverable | Gate |
| --- | --- | --- |
| Private POC | Desktop-managed restricted MCP over official tunnel | Real ChatGPT retrieval/viewer and denial tests pass |
| Relay alpha | Public HTTPS MCP with one enrolled device per tester | Two-account isolation, identity linking, local grants, cancellation, and revocation verified |
| Private beta | Installer enrollment, background option, diagnostics | Sleep/wake, upgrades, expired tokens, large previews, and service outage tests pass |
| Public submission | Reviewable plugin, support and privacy documentation | Current OpenAI requirements satisfied; review outcome confirmed |

Before beta, test cross-account/device routing attacks, stolen/revoked tokens,
grant changes mid-request, path escapes, stale citations, malformed archives,
oversized payloads, reconnect storms, and accidental payload logging. Use a
synthetic reviewer library to demonstrate behavior without real customer files.
Remote parsing/rendering of document attachments remains a resource and attack
surface even though tools are read-only; isolate workers and keep dependencies
patched.

## Decisions still needed

- Confirm publication accepts the device-dependent workflow and its offline UX.
- Select identity provider, hosting region, metadata retention, and support model.
- Decide whether approved users may browse whole documents or only cited regions;
  the existing viewer can navigate beyond the original citation.
- Establish identity recovery/device replacement without retaining library data.
- Measure relay bandwidth and rendering limits before setting quotas or pricing.
- Decide later whether to offer a self-hosted relay; it should share the transport
  contract without changing archive portability.

The production investment is primarily identity, device management, reliable
routing, and operations. Preserve the POC's access policy, packaged runtime,
retrieval implementation, and citation viewer behind that new transport.
