# VOPT release policy

An extraction workspace contains source content; a discovery catalog contains explicitly released metadata. They are different artifacts with different audiences. Never distribute the research/source archive as a discovery bundle.

## Profiles

Coverage permits document/model identity, revision, category, request reference, processing state, and reviewed attribute/qualifier presence. It excludes values, units, tolerances, conditions, OCR, quotations, images, file paths and source URLs. Identity strings can contain descriptive information, so review those fields too; field suppression alone is not classification review.

Values additionally permits finite canonical quantities/ranges, structured tolerance and reviewed operating-condition labels. Unresolved compact fractions, discrete configurations, approximation without bounds, and missing footnotes cannot silently become certain numeric filters. Source context remains private. Human review is required by default; agent/fixture exports explicitly identify development use in their generating workflow.

## Controls implemented

Strict field/type validation and canonical SHA-256 sealing; monotonic catalog sequence; cumulative revocation lists; policy-version increase for release changes; atomic full replacement; history retention only when allowed by the newest policy; secure deletion plus transactional FTS recreation. Readers hold a consistent SQLite snapshot. A failed import leaves the previous catalog intact.

Reviews bind the complete extraction fingerprint and current assertion review event. Re-extraction or source/metadata change makes old decisions stale; concurrent edits require a refresh. Corrections preserve original candidate/evidence. Successful primary and inherited context pages are required for release.

## Trust and distribution limits

Hash sealing checks corruption, not signer identity or authorization. The current local deployment trusts the operator selecting an import file. Reviewer names are labels, not authenticated organizational identities. For an operational transfer service, add an authenticated release authority, signature verification/trust-root distribution, schema migration policy, per-field policy review and target-environment approval.

A disconnected installation learns withdrawals only through an explicit new import. Revocation-safe rollback operates within that catalog's retained history; it cannot erase external copies/backups or prevent a user constructing a different database. An upstream revision does not silently mutate a downstream frozen export. These limits are part of the operating model, not claims of cross-domain security accreditation.
