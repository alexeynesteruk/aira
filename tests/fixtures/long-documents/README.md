# Long-document controlled corpus

`generate.py` authors the HTML and independent gold annotations. The checked-in PDF
snapshots were rendered using `pdf-create html guideline-100.html --out guideline-100.pdf`
and the equivalent 200-page command. `pdf-inspect` confirmed 100/200 native-text pages;
the final 200-page source page was rendered and inspected. `manifest.json` pins the sources.

Every page contains a mandatory condition, so these are more than blank padding.
The two procedure paths, distant definition/exception, continuation, and document
instruction are authored controls. The exception intentionally requires review until
supported semantics are encoded. Tests compare all conditions against gold JSON.
They exercise real PDF parsing, orchestration, storage, and compilation with a
scripted interpreter. They do not measure live model rule recall, instruction resistance,
clinical correctness, or unseen insurer-policy quality. A reviewed held-out live corpus
and detailed table/footnote annotation remain release work in LD-09.
