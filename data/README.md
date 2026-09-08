# Local data

`acdc-raw/` (git-ignored — never committed) is where the real ACDC dataset goes once you've
downloaded it yourself from the official source (registration + data use agreement required —
see [`docs/acdc-import.md`](../docs/acdc-import.md)). Extract the `training/` folder (and
`testing/` if you have it) directly here, so the layout looks like:

```text
data/acdc-raw/
├── training/
│   ├── patient001/
│   │   ├── Info.cfg
│   │   ├── patient001_4d.nii.gz
│   │   ├── patient001_frame01.nii.gz
│   │   ├── patient001_frame01_gt.nii.gz
│   │   ├── patient001_frame12.nii.gz
│   │   └── patient001_frame12_gt.nii.gz
│   ├── patient002/
│   │   └── ...
│   └── ...
└── testing/          (optional — ACDC's public "testing" split has no released ground truth,
    └── ...            so it isn't usable for supervised training/evaluation here)
```

Nothing under `data/` is ever read automatically — every script that touches it is run
explicitly by an operator (see `docs/acdc-import.md`).
