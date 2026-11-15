# Company-wide venture portfolio

The venture portfolio is separate from the operating-business registry. It allows OpenCompany to discover opportunities across different legitimate business models—physical products, digital downloads, software, subscriptions, services, content, licensing, partnerships, and future categories—without hard-coding the company to its initial three businesses.

## Lifecycle

1. `discovered`: an idea/opportunity is recorded.
2. `researching`: evidence gathering and validation are in progress.
3. `validated`: the opportunity has sufficient evidence for an owner decision.
4. `rejected`: the opportunity is not pursued; it may return to research if new evidence appears.
5. `approved_to_launch`: the owner explicitly authorizes launch planning.
6. `launched`: the owner explicitly confirms that the venture has actually launched.

Every status change is recorded in a venture event history. Evidence URLs must use HTTPS. The API is owner-authenticated.

## Separation from operating units

An opportunity is not a customer order, a product catalogue entry, or an operating business unit. Recording or validating an opportunity does not create accounts, credentials, storefronts, inventory, financial ledgers, or customer records. The owner must approve launch before a separate operating unit and its scoped resources are provisioned. The original physical-agency, physical-brand, and digital-products units remain separate; none can fulfil another unit's customer promise by substituting an unrelated product or service.

## API

- `GET /venture-opportunities` — list the owner portfolio, optionally filtered by status.
- `POST /venture-opportunities` — record a new opportunity with a free-form business-model category.
- `POST /venture-opportunities/{id}/status` — advance through the guarded lifecycle; launch approval and launch confirmation require explicit owner confirmation.
- `GET /venture-opportunities/{id}/events` — inspect the recorded status history.

These endpoints do not run external research, spend money, contact customers, publish listings, create accounts, or launch a business.
