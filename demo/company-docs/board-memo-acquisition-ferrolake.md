# Board Memo: Proposed Acquisition of Ferrolake Data Systems

> **CONFIDENTIAL** | Calloway Metrics, Inc.

| Version | Date | Owner | Distribution | Change |
|---|---|---|---|---|
| v1.2 | Sep 14, 2026 | Dana Whitcombe (CEO) | Board of Directors; R. Okafor (CFO); L. Brandt (GC) | fixed earnout number per Raj, was 5.5 |

To: Board of Directors, Calloway Metrics. From: Office of the CEO. Date: September 14, 2026. Classification: CONFIDENTIAL, Board Eyes Only. This memo requests board approval to enter exclusive negotiations to acquire Ferrolake Data Systems, a 64 person streaming ingestion startup based in Rotterdam, for a total enterprise value of up to 41.5 million dollars.

Strategic rationale. Our largest enterprise customers have told us for three consecutive quarters that batch refresh windows of four hours are no longer acceptable. Ferrolake built a change data capture engine, internally called Tidewater, that streams warehouse updates with a median latency of 900 milliseconds. Building an equivalent engine in house would take an estimated 22 engineer quarters and delay our real time dashboards product until at least Q3 2028. Acquiring Ferrolake brings the product to market in Q2 2027.

Financial summary. Ferrolake reported trailing twelve month revenue of 6.2 million dollars with 71 percent gross margin and net revenue retention of 118 percent. The company burns roughly 480,000 dollars per month and has 7 months of runway, which gives us meaningful leverage on price. The proposed structure is 24 million dollars in cash at close, 11.5 million dollars in Calloway stock, and an earnout of up to 6 million dollars tied to Tidewater reaching 40 enterprise deployments by December 2027.

- Cash at close: 24.0 million dollars, funded from the existing balance sheet
- Stock consideration: 11.5 million dollars at the Series D price of 18.40 dollars per share
- Earnout: up to 6.0 million dollars over 15 months
- Retention pool: 3.2 million dollars for the 12 key engineers, vesting over 3 years
- Expected close: January 2027, pending Dutch works council consultation

Risks. The principal risk is founder retention. Ferrolake CTO Maren Oosterbeek holds the core architectural knowledge for Tidewater, and our diligence team rates the codebase as poorly documented. We propose a personal retention agreement for her of 1.1 million dollars over three years. A second risk is that Ferrolake's two largest customers, which together account for 38 percent of revenue, have change of control clauses. Legal counsel believes both will consent, but we have not yet approached them.

Competitive considerations. We understand that Quillmark Software also approached Ferrolake in July. Our banker believes Quillmark offered approximately 35 million dollars, mostly in stock. Speed matters, and we recommend a signed letter of intent within 21 days. The exclusivity period should be 45 days with a break fee of 1.5 million dollars payable by Ferrolake if they walk.

Integration plan. Ferrolake would operate as a standalone unit for the first two quarters, reporting to our VP of Platform. In Q3 2027 we would migrate Tidewater onto the Calloway control plane and retire Ferrolake's separate billing system. We anticipate eliminating 9 overlapping roles in sales operations and finance, with associated severance of roughly 640,000 dollars.

Note from Raj (CFO), added 9/13: the 41.5 number is our walk away, NOT the opening offer. open at 34-35 and let them come to us. also we still dont have the Q2 audited numbers from Ferrolake, only mgmt accounts, so treat the 6.2M TTM as soft.

## Appendix A: Valuation cross check

| Method | Low ($M) | Mid ($M) | High ($M) | Notes |
|---|---|---|---|---|
| ARR multiple (5.5x to 7.0x) | 34.1 | 38.8 | 43.4 | peer set of 9 private infra deals 2024-2026 |
| Build vs buy cost avoided | 29.0 | 33.5 | 38.0 | 22 eng quarters at loaded cost, plus 5 quarters of delay |
| DCF, 5 yr, 14% WACC | 31.7 | 36.9 | 44.2 | assumes Riptrace attach on 25% of Enterprise base |
| Quillmark-implied bid | n/a | 35.0 | n/a | banker estimate, mostly stock |

The ranges overlap reasonably well between 34 and 39 million. We think 41.5 million is defensible only with the earnout, which shifts 6 million of risk back onto the sellers. Finance did NOT model a scenario where Ferrolake's two big customers refuse consent; in that case revenue drops to around 3.8 million and we would want to renegotiate the headline price, probably by 8 to 10 million.

## Appendix B: Diligence status

| Workstream | Lead | Status | Open items |
|---|---|---|---|
| Financial | R. Okafor | 70% | audited FY25, deferred revenue schedule |
| Legal / IP | L. Brandt | 55% | 3 GPL dependencies in log reader, contributor agreements for 2 ex-employees |
| Technical | A. Novak | 80% | load test at 3x peak, docs review |
| People | P. Ramanathan | 40% | works council timeline, Dutch employment terms |
| Security | K. Torres | 60% | pen test report is from 2024, need fresh one |

Note on the GPL issue: Ferrolake's Rust log reader vendors a small GPL licensed parsing crate. Novak's view is that it can be replaced in about three weeks. We should make replacement a pre close covenant rather than a price adjustment.

## Appendix C: Key people

Maren Oosterbeek, co-founder and CTO, 11 years at large Dutch payments processor before Ferrolake, holds both patents filed by the company. Joost van Tiel, co-founder and CEO, commercial background, would likely leave after 12 months and we are comfortable with that. Head of engineering Ilse Brouwer runs the 23 person core team and is considered the strongest manager in the org by our diligence interviews; she is not currently in the retention pool and we think she should be, at roughly 400k over three years.

Board members with questions before the 22nd should contact Dana directly rather than replying on the board portal thread, since the portal is shared with observers from two funds that also hold positions in Quillmark.

Recommendation. Management recommends that the board authorize the CEO to sign a non binding letter of intent on the terms above, with a ceiling enterprise value of 41.5 million dollars, and to engage Halvorsen Partners as financial advisor at a fee of 1.2 percent of transaction value. Please do not forward this memo. Discussion will take place in the closed session on September 22.

