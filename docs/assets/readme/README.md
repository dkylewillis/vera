# README media checklist

This directory holds optimized media used by the repository's root README.
The README already contains the final `<img>` markup for each capture inside
`<!-- TODO(assets) -->` comments — add the file here, then uncomment the
matching block. Do not include API keys, personal account details, local file
paths, or confidential source documents in any capture.

## Required still images

| File | Capture | README use |
| --- | --- | --- |
| `hero-grounded-answer.png` | An Ask answer beside its source PDF, with an opened citation and highlight. | Product proof immediately below the introduction. |
| `provider-setup.png` | The **LLM Providers** dialog with a provider, empty/redacted **API Key** field, enabled model, and **Set as active** control. | Step 2–4 of desktop quick start. |
| `convert-single-pdf.png` | The **Convert PDF** view with a PDF selection / directory conversion. | Conversion feature card and quick start. |
| `library-indexing.png` | A selected library with its index status, build/update prompt, or completed index. | Library indexing feature card. |
| `citation-in-source.png` | An answer citation selected in the source document viewer. | Grounded answer feature card. |

Use PNG files around 1400–1800 px wide, preserve readable UI text at their
rendered README size, and keep the window size and theme consistent.

## Feature tour video

Record a 20–30 second tour:

1. Add a provider, save an API key, and select/enable a model.
2. Convert one PDF.
3. Select the resulting library and build its index.
4. Ask a question, then select a citation to show its source.

Upload the video to a GitHub Release or an external video host, then replace
the video `TODO(assets)` comment near the top of the root README with a link
to it. Do not commit a large video file to this repository.
