# Native PDF parser fixtures

These are fictional layout and failure fixtures, separate from the independently annotated clinical scenarios in `../scenarios/`. They contain no real patient record or payer policy. The [manifest](manifest.json) records exact PDF hashes, construction commands, purposes, page counts, and inspection outcomes.

HTML sources were rendered using the local `pdf-tools` skill. `assets/native-layout_p001.png` was rendered from the native fixture and embedded to produce image-only and mixed-content examples. The public test password is `fixture-only`. Combined files were created only after inspecting their inputs and reviewing the `pdf-merge --dry-run` page order. The encrypted PDF is intentionally unreadable without a password.

`annotation-only.pdf` adds a sticky-note amendment to an otherwise blank page. `native-with-annotation.pdf` adds a visible strikeout to a native measurement. Both were created with `pdf-annotate`, inspected, and rendered; neither may pass native extraction. `navigation-link.pdf` checks the narrow exception for a noncontent link while retaining the visible native label. Additional Link appearance/text/action cases use controlled metadata in tests and are labeled accordingly.

Tests consume the checked-in PDFs; they do not require `pdf-tools`, a browser, or a provider key. Regeneration is an explicit authoring action and may change bytes or typography because of rendering/font versions. Inspect/render regenerated PDFs and review assertions before changing their recorded hashes. Malformed inputs are deliberately invalid byte strings in the integration tests; no original document was damaged to create them.

The [extraction report](../../../docs/results/pdf-extraction.md) records tested behavior and current limitations. Passing parser tests is not evidence of live model quality or clinical correctness.
