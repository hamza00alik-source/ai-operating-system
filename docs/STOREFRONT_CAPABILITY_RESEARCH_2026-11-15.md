# Storefront capability and payout research — 2026-11-15

This is a research snapshot, not account verification. Country eligibility, KYC acceptance, payment setup, fee schedules, API scopes, and seller account status can change. A channel must not be marked connected or verified until the owner completes its account-specific checks.

## Executive recommendation

1. Keep WooCommerce as the owned storefront for the own-brand physical business and digital products. Existing integration work should be reused; this document does not claim that the account connection is live.
2. Prioritize Gumroad for digital downloads because its official payout help explicitly lists Pakistan with local PKR bank payouts and there is no monthly subscription. Keep product creation/upload manual: Gumroad's help center explicitly says its API cannot create products or upload content.
3. Prioritize CGTrader for 3D assets after the seller dashboard confirms payout method availability. CGTrader advertises an OAuth 2.0 developer API and inbound capabilities for uploading models, creating drafts, finalizing unpublished models, and updating models. Payoneer availability depends on location; do not assume it is enabled for this account.
4. Keep itch.io as a strong game-download channel only after account payout settings confirm Payoneer is available. The platform's collected-payout mode supports PayPal or Payoneer, but the current API reference is principally profile/game/purchase verification—not listing creation or upload.
5. Defer Etsy while the company is at PKR 0: Pakistan is eligible for Etsy Payments via Payoneer, but each listing costs $0.20, the transaction fee is 6.5%, and Pakistan payment processing is 6.5% + $0.30 USD; a location-dependent setup fee may also apply.
6. Defer Fab and Unity Asset Store until seller onboarding and Pakistan payout route are verified. They are useful later-stage 3D/game-asset channels but not yet approved for automated integration.

## Verified official facts

| Channel | Seller/payout evidence | Fees / thresholds | Automation boundary | Current disposition |
|---|---|---|---|---|
| WooCommerce | Owned-store target; no account-level connection verified here | Hosting, domain, payment gateway and transaction costs depend on chosen setup | Existing code must be reviewed before reuse; credentials remain owner-managed | Keep primary, connection unverified |
| Gumroad | Official payout page lists Pakistan bank payout in PKR. Payouts require identity and residence/business evidence. | Direct/profile sales: 10% + $0.50 plus card processing (2.9% + $0.30) or PayPal fees. Discover marketplace sales: 30% inclusive of processing. Standard payout threshold $100 USD; weekly/monthly/quarterly schedules; 7-day holding period for weekly/monthly/quarterly sales. No monthly fee. | Official Gumroad Help says the API cannot create products or upload content. API may still support read-side sales/product workflows; verify scopes separately. | Best first external digital-download candidate; internal listing packet + owner manual upload |
| itch.io | Collected-by-itch.io payout mode offers PayPal or Payoneer. Payout method and tax validation are account-specific; Pakistan-specific Payoneer acceptance must be checked in the seller account. | Seller chooses itch.io revenue share from 0–100% (example/default 10%); payment processing typically around $0.30 + 2.9%. Minimum payout $5, transaction hold 7 days, payout review at least 7 days and typically 10–14 days. A $3 tax-identity fee is charged once; default withholding may be 30% without a valid tax ID. | Official server API supports profile/game listing and purchase/download-key verification. The published reference does not document product creation/upload. Build/upload can be handled via the separate butler workflow; no automated upload is enabled here. | Candidate for game-related downloads after payout/KYC check; read-only API first |
| CGTrader | Official help says seller payouts use Hyperwallet and Payoneer may be available depending on location; verify inside payout settings. Payment agreement/KYC is required. | Official September 15, 2026 update: seller payout rate ranges from 55% to 80%, based on rolling 12-month net sales. | Developer page advertises OAuth 2.0 and an inbound API for bulk model upload, draft creation/finalization, and automatic model updates. Technical API access and account permission must be confirmed before implementation. | Best 3D-model channel candidate; API potential, account payout unverified |
| Etsy | Pakistan is eligible for Etsy Payments using a Payoneer Payment Account. | $0.20 per listing (four-month expiry), 6.5% transaction fee, Pakistan processing fee 6.5% + $0.30 USD; possible location-dependent shop setup fee and Payoneer withdrawal costs. | Etsy has a seller API, but no API integration is authorized by this research; listing fee makes it non-zero-budget. | Disabled until owner approves listing/setup fees |
| Fab | Publisher setup requires trader verification and third-party payout setup. Pakistan route not confirmed by the official material reviewed. | Publisher receives 88% of revenue. Payments approximately 30 days after month-end when at least $100 USD is due; lower balances roll over. | Official publisher workflow is portal-based: create listing, upload assets, submit for review, then publish. No public seller listing API was verified. | Later-stage/manual candidate; country payout and API status unverified |
| Unity Asset Store | Payout profile supports monthly PayPal or quarterly bank transfer; payout currency is USD. Pakistan eligibility for the selected payout provider was not confirmed. | Exact publisher payout percentage/fees and Pakistan bank routing require account/publisher terms review. | Official workflow uses Unity Editor Asset Store Publishing Tools to validate/upload unitypackage files, then Publisher Portal submission/review. No public upload API was verified. | Later-stage/manual candidate; require payout-country check |

### Gumroad MCP update

Gumroad now also documents an official remote MCP connector for compatible AI assistants. Its public product page describes reading products, sales and payouts, preparing product drafts, and publishing them; the product files still need to be added in Gumroad before publication. This is separate from the standard v2 API limitation described above. It is not currently wired into the OpenCompany runtime, and it must not be treated as an enabled OpenCompany integration. Any future connection must use owner-authorized OAuth, least-privilege scopes, and an explicit per-action approval gate; publishing remains disabled by default.

Official references:
- Gumroad MCP capabilities: https://gumroad.com/mcp
- Gumroad Help explanation of the MCP connector: https://gumroad.com/help/article/355-connect-ai-assistants-to-gumroad

## Official source links

### Gumroad
- Getting paid and country-specific payout table: https://gumroad.com/help/article/13-getting-paid
- Gumroad fees: https://gumroad.com/help/article/66-gumroads-fees
- API limitation on creating products/uploading content: https://gumroad.com/help/article/76-license-keys

### itch.io
- Payments, payout eligibility, payout methods and tax withholding: https://itch.io/docs/creators/payments
- Server-side API reference and published endpoints: https://itch.io/docs/api/serverside
- API overview: https://itch.io/docs/api/overview

### CGTrader
- Developer API and OAuth 2.0 / inbound upload capabilities: https://www.cgtrader.com/developers
- Payout methods and location-dependent Payoneer availability: https://help.cgtrader.com/hc/en-us/articles/360015145137-payout-methods
- Seller payout timing and payment agreement: https://help.cgtrader.com/hc/en-us/articles/360015145117-i-just-sold-my-model-when-will-i-get-paid
- Payout rate update effective September 15, 2026: https://help.cgtrader.com/hc/en-us/articles/50374021634833-payout-rate-update-september-15-2026-faq

### Etsy
- Countries eligible for Etsy Payments: https://help.etsy.com/hc/en-us/articles/115015710408-countries-eligible-for-etsy-payments
- Payoneer onboarding: https://help.etsy.com/hc/en-us/articles/16999319005207-how-do-i-use-a-payoneer-account-with-etsy-payments
- Seller fees: https://help.etsy.com/hc/en-us/articles/115014483627-what-are-the-fees-and-taxes-for-selling-on-etsy
- Pakistan payment-processing fee: https://help.etsy.com/hc/en-us/articles/115015628847-what-are-the-payment-processing-fees-for-selling-on-etsy

### Fab
- Publisher onboarding, 88% revenue share, payout threshold and payout timing: https://dev.epicgames.com/documentation/fab/publisher-get-started-in-fab
- Listing workflow and review-before-publication: https://dev.epicgames.com/documentation/fab/publishing-assets-for-sale-or-free-download-in-fab

### Unity Asset Store
- Publisher payout profile and USD-only payout currency: https://docs.unity.com/en-us/asset-store/publishing/asset-packages/revenue/payouts
- Asset Store Publishing Tools upload/validation workflow: https://docs.unity.com/en-us/asset-store/publishing/asset-packages/upload
- Submission review workflow: https://docs.unity.com/en-us/asset-store/publishing/asset-packages/submit

## Owner/account checks still required

These checks are not suitable for autonomous execution because they involve personal identity, payout setup, account permissions or fee acceptance:

1. Gumroad: confirm the account's Pakistan bank payout settings, identity/residence requirements and live payout minimum shown in Payments settings.
2. itch.io: confirm the account can select Payoneer under Collected by itch.io payouts, complete tax interview, and review the withholding rate.
3. CGTrader: confirm Payoneer or Hyperwallet availability and complete the seller payment agreement; request API access and review OAuth scopes.
4. Etsy: do not proceed unless owner explicitly approves the one-time setup fee and $0.20 listing charges.
5. Fab: complete publisher/trader verification and confirm third-party payout provider accepts the seller's country.
6. Unity: confirm that the publisher payout profile supports the seller's country and chosen bank/PayPal rail.

No credentials should be added to Git. Store them only in the owner-controlled secret vault/environment. No channel should be activated or written to until these checks and a separate owner approval are recorded.
