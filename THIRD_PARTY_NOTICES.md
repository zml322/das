# DASexplorer annotation code

`utils/classes/annotation_canvas.py` incorporates and adapts code from the
user-provided DASexplorer checkout at `D:/projects/DASexplorer`:

- `dasexplorer/gui/waterfall.py`: AnnotationROI, OBBCurveItem, PolylineItem,
  ScatterAnnotItem, BBox/multipoint creation and completion workflows;
  draggable TargetItem editing, screen-space hit testing, and OBB workflow.
- `dasexplorer/core/annotations_model.py`: annotation type conventions.

Copyright (C) 2024-2026 Sergio Morell-Monzó.
Institut d'Investigació per a la Gestió Integrada de Zones Costaneres (IGIC-UPV),
Universitat Politècnica de València.

The reference project is licensed under GNU GPL version 3 or, at your option,
any later version. Its original license notice is reproduced in
`licenses/DASexplorer-LICENSE.txt`.

Modifications in DASViewer v2.1.25 adapt the drawing tools to an existing
PyQtGraph PlotWidget, add Chinese UI, store original sample/channel vertices,
persist camera/DAS alignment, and integrate edit/undo/CSV workflows.

The versioned Windows build includes this notice and the original license.
Its sibling `DASViewer-v2.1.25-source.zip` contains the application source,
requirements and build scripts used to produce the executable.

# das_veh vehicle tracking code

`utils/vendor/das_veh/tracking.py` and `car_tracking_utils.py` incorporate code
from https://github.com/syyuan93/das_veh at commit
`b1831d2d2a5636ec416095f9647a33881afaeed1`.

Copyright (c) 2023 Siyuan Yuan. MIT license; the complete license is reproduced
in `licenses/das_veh-LICENSE.txt`. The upstream attribution to TelecomTM is
preserved. Source adaptation details are in `utils/vendor/das_veh/UPSTREAM.md`.

DASViewer adds original-sampling-rate BIN adaptation, coordinate mapping,
background cancellation, parameter controls and candidate review/storage.
