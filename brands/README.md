# Brand artwork

**Home Assistant does not load branding from `custom_components/`.** The
frontend fetches brand images from `brands.home-assistant.io`. Until the files
here are merged into the brands repository, the integration shows the generic
fallback icon no matter what is in your config directory.

## Submitting

1. Fork https://github.com/home-assistant/brands
2. Create `custom_integrations/xweather_lightning/`
3. Copy `icon.png`, `icon@2x.png`, `logo.png`, and `logo@2x.png` into it
4. Open a PR

Custom integrations go under `custom_integrations/`, not `core_integrations/`.
The directory name must match the manifest `domain` exactly:
`xweather_lightning`.

## The copy under custom_components/

`custom_components/xweather_lightning/brand/` holds the same four files.
Home Assistant ignores them, but HACS checks that path before falling back to
the brands repository, so their presence is what keeps its brands check green.
Regenerating the artwork here means copying it there too.

## Files

| File | Size |
|---|---|
| `icon.png` | 256x256 square |
| `icon@2x.png` | 512x512 square |
| `logo.png` | 270x256 |
| `logo@2x.png` | 540x512 |
| `source-logo.png` | 1312x1199 original, kept for regeneration |

All are trimmed to the alpha bounding box with transparency preserved. The
source already had a clean alpha channel — no white matting to key out — so
edges keep their soft glow falloff and show no fringing on Home Assistant's
dark default theme.

Verify the size requirements against the brands repository README before
opening the PR; they can change.

## Regenerating

```bash
python3 scripts/make_brand_assets.py brands/source-logo.png brands
```

Writes all four assets plus `preview-dark.png` and `preview-light.png` for
checking edge fringing against both themes. The previews are gitignored.
