# Capability Selector Schema

Each selector in `capabilities.json` identifies an OOXML element by package-part glob, namespace,
local name, and optional attribute constraints. The optional `parent` object narrows a match to an
element whose **direct XML parent** has the declared namespace and one of the declared local names:

```json
{
  "partGlob": "ppt/slides/slide*.xml",
  "namespace": "http://schemas.openxmlformats.org/drawingml/2006/main",
  "localName": "scene3d",
  "parent": {
    "namespace": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "localNames": ["grpSpPr", "spPr"]
  }
}
```

`parent` is an exact semantic constraint, not an ancestor search. Its namespace and nonempty,
duplicate-free `localNames` list are both required. Omitting `parent` preserves the original
unscoped selector behavior and fingerprint representation.

This distinction matters for DrawingML 3D. An `a:scene3d` directly under `p:spPr` or `p:grpSpPr`
is shape/group scene data. The same element directly under `a:bodyPr` is text-body 3D and is
tracked separately. Inventory observation does not imply renderer support; the capability's
`renderMode`, bounded scope, gates, and fresh promotion receipt determine the support claim.

The inventory scanner enforces direct-parent matching while streaming XML with a bounded ancestor
stack. Contract and scanner behavior are covered by `test_capability_contract.py` and
`test_capability_inventory.py`.

See `CORPUS_CLASSIFICATION.md` for the separate representative-versus-validation ranking signal.
