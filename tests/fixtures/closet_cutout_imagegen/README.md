# Closet Cutout Imagegen Test Set

This fixture directory defines a synthetic image-generation test set for the selfit electronic closet cutout pipeline.

Use it to generate controlled images, import them through `/closet/import/upload`, and evaluate whether the system correctly finds garments, classifies them, creates masks/cutouts, and assigns `usable/review/rejected`.

## Files

- `manifest.json`: authoritative case list, grouped by risk area.
- `prompts/*.md`: human-readable prompt sheets by category.
- `generated/`: place generated images here. Use filenames like `A01_white_tshirt.png`.

## Recommended First Pass

Generate all `seed: true` cases first. They cover every category with a smaller run:

- `A01`, `B01`, `B02`, `C01`, `C02`, `C03`, `C04`, `D01`, `E01`, `F01`, `G01`, `H01`, `I01`, `J01`, `K01`, `L01`, `M01`, `N01`, `O01`, `P01`, `Q01`, `R01`, `S01`, `T01`

`B02` and `C02`–`C04` are the multi-item regression core. They cover a model-worn outfit, a clean four-item flatlay, a dress that must remain one garment, and a lightly overlapping four-item outfit.

Then expand to the full 100-case set once the pipeline is stable.

## Evaluation Fields

For each generated image, record:

- `found`: whether any closet item was created.
- `actual_count`: number of generated closet items.
- `category_accuracy`: `correct | partial | wrong`.
- `edge_quality`: `good | acceptable | bad`.
- `background_residue`: `none | slight | heavy`.
- `subject_loss`: `none | slight | heavy`.
- `closet_quality`: `usable | review | rejected`.
- `tryon_ready`: `yes | no`.
- `notes`: short reason, such as "shoe laces missing" or "white skirt edge lost".
