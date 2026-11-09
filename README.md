# Documentation claim auditor

Version 0.1.0. An offline, deterministic, standard-library-only CLI for Python
3.9+ that checks documentation about changing a picture's pixel dimensions
against static source patterns. No LLM, network, telemetry, or filesystem writes.
MIT licensed.

## Install and run

```sh
python3 -m pip install .
image-resizing-claim-audit --version
image-resizing-claim-audit audit . --json
python3 -m image_resizing_claim_audit audit . --verbose
image-resizing-claim-audit audit --ignore docs/archive/ . --fail-on medium
python3 -m unittest discover
python3 -m build
```

The repository defaults to the current directory. Repeat the single-value ignore
option for multiple path prefixes. Verbose scan scope and per-file decisions go
to stderr. JSON goes to stdout, with verdict and message fields on each finding.
Exit codes are 0 for a pass, 2 for findings at the selected threshold, and 1 for
usage or IO errors. The default threshold is high; medium also fails test-only
claims. Each rule family yields at most one finding.

```text
documented-image-resizing-claim-false (high; test-only: medium)
documented-no-image-resizing-claim-false (high)
```

## Scope and matching

Scans root README.md and Markdown below docs/. Triple-backtick fenced blocks are
excluded; inline code counts as prose. Matching uses case-insensitive exact
substrings, without stemming or hyphen normalization. Denial spans are removed
first. Longest-first matching makes each occurrence match once under its longest
phrase. No claims is a pass; a denial without contrary code is a pass. Test
fixtures under tests/ can produce a medium finding.

Every repository source file with a .py suffix is checked independently, excluding
Git metadata, bytecode caches and virtual environments. Each paired route must
occur within one module. Imports and aliases are resolved; local function or
class definitions shadow route names. The recognized patterns are:

```text
PIL: Image.open(...) traced to an assigned object followed by .resize(...) or
  .thumbnail(...), or the same calls chained directly; ImageOps.fit(...)
cv2: resize(...) via the module or a from-import
skimage.transform: resize(...) via the module or a from-import
torchvision.transforms / torchvision.transforms.v2: Resize(...) construction
  followed by a call on the resulting object, assigned or chained
Generic route: x.resize_image(...) or a from-imported/aliased bare call
```

Bare imports, opening alone, untraced methods, unbound names, construction alone,
strings, comments, subprocess commands and evidence split across modules do not
qualify. Array storage changes, cropping, rotation, flipping and neighboring
capabilities alone provide no evidence.

## Differentiation

```text
image-classification-claim-audit
```

Checks assigning one label to a whole picture. This tool checks changing a
picture's pixel dimensions.

```text
image-background-removal-claim-audit
```

Checks cutting a subject out of a picture. This tool checks changing a picture's
pixel dimensions.

```text
super-resolution-claim-audit
```

Checks model-based upscaling of one picture. This tool checks plain dimension-change
calls; learned upscaling alone does not qualify.

```text
image-inpainting-claim-audit
```

Checks filling a hole in one picture. This tool checks changing a picture's pixel
dimensions.

```text
image-colorization-claim-audit
```

Checks adding color to a grey picture. This tool checks changing a picture's pixel
dimensions.

```text
image-object-detection-claim-audit
```

Checks finding and boxing things in one picture. This tool checks changing a
picture's pixel dimensions.

```text
image-stitching-claim-audit
```

Checks joining overlapping pictures into one wide picture. This tool checks
changing one picture's pixel dimensions.

## Limitations

Static pattern matching is not semantic judgement or proof of working behavior.
Exact phrases miss restatements. The first phrase below can also describe
normalising pixel values to a range; the second can also describe ML feature
scaling. Both still match as documented ambiguities.

```text
scale images
image scaling
```

The following call on a non-picture array still counts as evidence, since the
call form is shared:

```python
cv2.resize(array, size)
```

The following operation also crops as well as changing dimensions:

```python
ImageOps.fit(picture, size)
```

A generic call on an unrelated object counts as evidence via the generic route,
since the method name is shared:

```python
object.resize_image(value)
```

For a README-only self-check, copy this README into an otherwise empty directory
and audit that directory. The full checkout contains phrase-oracle fixtures in
tests/ and therefore produces the expected medium finding.
