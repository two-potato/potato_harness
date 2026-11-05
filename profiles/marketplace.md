# Marketplace engineering profile

Apply the checks below to the capabilities changed by the task. Use the task
contract and verified project behavior for project-specific decisions. Report
missing or conflicting business rules. Request a decision if the ambiguity
affects acceptance, access, money, inventory, or a state transition. This profile
adds engineering checks under the existing Harness permissions and risk policy.

| Capability | Checks to consider when affected |
| --- | --- |
| Actors and ownership | Identify actors and resource owners. Check access at the server boundary, including attempts to read or mutate another seller's or buyer's resources. |
| Catalog and discovery | Distinguish products, listings and variants where the project models them. Verify visibility, publication state, filters and stale-index behavior. |
| Pricing and promotions | Identify the authoritative amount, currency, rounding and quote lifetime. Cover stale quotes and boundaries for stacking, taxes or discounts where applicable. |
| Availability and allocation | Identify the source of availability and any reservation expiry. Exercise concurrent allocation, cancellation and duplicate requests where applicable. |
| Orders, bookings and fulfillment | Use the project's allowed state transitions and actor permissions. Cover cancellation, repeated or out-of-order events, and partial fulfillment where supported. |
| Payments, refunds and payouts | Validate provider event authenticity, idempotency and reconciliation where supported. Verify amounts and authorized transitions using synthetic data and sandbox providers. |
| Trust and privacy | Check abuse cases, moderation and exposure of buyer or seller data where applicable. Keep personal data and credentials out of fixtures, logs and optimization traces. |

Describe applicable checks, expected behavior and evidence. Mark unsupported or
unaffected capabilities as not applicable. Obtain commands and fixtures from the
operator-approved task. Existing acceptance checks and escalation rules apply
regardless of what the agent reports.
