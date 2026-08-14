# How Paperplane works

1. The browser sends one document and processing mode to `POST /v2/parse`.
2. The API validates size, type, page count, and decoded-image limits.
3. PyMuPDF renders each page and collects usable native PDF words.
4. Luna produces an ordered structured page draft.
5. Deterministic geometry checks ground content and identify ambiguity.
6. Terra verifies only the content allowed by the selected mode's bounded budget.
7. The backend assembles grounded Markdown and hierarchical JSON and returns them directly.

Fast minimizes model work, Balanced verifies flagged content, and Audit spends the largest
verification budget. The processing is bounded rather than an open-ended agent loop.

No application state is written between requests. Saving or indexing a result is the
caller's responsibility.
