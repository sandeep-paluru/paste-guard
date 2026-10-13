# Product Roadmap 2027 (Internal Draft v3)

> **CONFIDENTIAL** | Calloway Metrics, Inc.

| Version | Date | Owner | Distribution | Change |
|---|---|---|---|---|
| draft v3 | Oct 8, 2026 | Marcus Feld (VP Product) | Product leads, EM staff | Lantern moved to Q3 (was Q2) |

CONFIDENTIAL. Product Management. This roadmap reflects planning as of October 2026 and assumes the Ferrolake acquisition closes in January. Dates are internal targets and must not be communicated to customers. External roadmap messaging is maintained separately by Product Marketing.

Themes. The 2027 roadmap is organized around three themes: real time everything, the AI analyst, and enterprise trust. Together these are expected to drive 60 percent of 2027 net new ARR. Investment allocation is 40 percent real time, 35 percent AI analyst, and 25 percent enterprise trust.

- Q1 2027: Tidewater private beta with 12 design partners; AI query assistant general availability; SOC 2 Type II renewal
- Q2 2027: Real time dashboards general availability; streaming usage billing; customer managed encryption keys
- Q3 2027: AI analyst agent, codename Lantern, private beta; Tidewater on the Calloway control plane
- Q4 2027: Lantern general availability; FedRAMP Moderate authorization in process; data residency in India and Brazil

Project Lantern. Lantern is an autonomous analyst that monitors key metrics, detects anomalies and drafts written explanations for business users. It will use a fine tuned open weight model hosted in our own inference cluster rather than a third party API, which reduces per query cost by an estimated 64 percent and addresses data residency objections from regulated customers. The team is 14 engineers and is currently understaffed by four.

Deprioritized items. We will not build a native mobile app in 2027. The embedded analytics SDK is paused until Q1 2028. The legacy reporting module will enter end of life in Q3 2027, affecting about 210 customers, who will be offered free migration services.

Dependencies and risks. Real time dashboards depend entirely on Tidewater. If the Ferrolake deal fails, the fallback is a reduced latency batch mode with 5 minute refresh, which we believe is insufficient to retain Cedarpoint and Harborline. Lantern depends on hiring three ML infrastructure engineers by February.

Pricing linkage. Lantern will be sold as an add on at an expected 30,000 dollars per year for Business and included in Enterprise Plus. Finance projects 3.1 million dollars of Lantern ARR by end of 2027.

Staffing plan. Real time work is staffed by the combined Platform and Ferrolake teams, totaling 31 engineers after close. The AI analyst theme has 22 engineers including Lantern. Enterprise trust has 16 engineers plus a dedicated compliance program manager. Headcount additions in 2027 are limited to 19 roles, all of which are allocated to Lantern and ML infrastructure. Any change to theme allocation above 5 percent requires approval from the CEO and the VP of Engineering at the quarterly planning review.

## Quarterly plan by team

| Team | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|
| Streaming (ex-Ferrolake) | Riptrace beta, 12 partners | dashboards GA | control plane migration | Oracle spike |
| Query engine | incremental aggregates | late events <24h | cost based caching | multi region reads |
| AI / Lantern | assistant GA | eval harness, data contracts | Lantern beta | Lantern GA |
| Trust | SOC 2 II renew | CMEK | FedRAMP readiness | India/Brazil residency |
| Growth | pricing v3 rollout | usage billing | self serve Team | PLG experiments |

## Lantern architecture sketch

```
  metrics store ---> anomaly detector ---> candidate events
                                             |
                                             v
  semantic layer <--- planner (LLM, 8B FT) ---> SQL tool ---> warehouse
                                             |
                                             v
                                   narrative writer ---> Slack / email / app
```

The planner model is an 8 billion parameter open weight model fine tuned on roughly 40,000 internal question to SQL pairs from design partners who consented. We tested a hosted frontier API as the planner and it was about 9 points better on our eval but 11x the cost per run, and three of our design partners will not allow data to leave their region.

## Success metrics

| Metric | Today | End 2027 target |
|---|---|---|
| Median dashboard freshness | 4h 10m | < 10 s for streaming tenants |
| Assistant weekly actives | 22,000 | 90,000 |
| Lantern tenants | 0 | 110 |
| Enterprise deals lost on security | 14% | < 6% |

There is still disagreement on whether self serve Team should ship in Q3 or slip to 2028. Sales leadership wants it delayed because it may cannibalize mid market AE pipeline. Marcus to bring a recommendation to the November staff meeting.

Please do not copy this roadmap into customer facing documents, slides, or AI tools. Questions go to the VP of Product.

