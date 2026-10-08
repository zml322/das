"""DAS annotation interactions adapted from DASexplorer.

Copyright (C) 2024-2026 Sergio Morell-Monzó, IGIC-UPV.
Original: dasexplorer/gui/waterfall.py (GPL-3.0-or-later).
Adaptation: external PlotWidget, canonical sample/channel geometry, Chinese UI.
See THIRD_PARTY_NOTICES.md and licenses/DASexplorer-LICENSE.txt.
"""
from enum import Enum
import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtGui, QtWidgets


class AnnType(str, Enum):
    BBOX = "bbox"
    OBB = "obb"
    KP = "kp"
    LINE = "lin"


TYPE_LABELS = {"bbox": "事件框", "obb": "倾斜框", "kp": "关键点", "lin": "轨迹线"}
COLORS = {"bbox": "#b05e00", "obb": "#9c3cac", "kp": "#087f8c", "lin": "#13734a"}


def _bbox_pen():
    return pg.mkPen(COLORS["bbox"], width=2)


_ANN_TYPE_PENS = {kind: (lambda k=kind: pg.mkPen(COLORS[k.value], width=2)) for kind in AnnType}


class AnnotationROI(pg.ROI):
    """Plain ROI that emits sigRightClicked instead of showing pyqtgraph's context menu.
    
    Stores its own `ann_index` attribute so the index can be updated in-place
    when other annotations are removed (avoids stale lambda captures).
    """
    sigRightClicked = QtCore.pyqtSignal(object)

    def __init__(self, *args, ann_index: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.ann_index = ann_index

    def mouseClickEvent(self, ev) -> None:
        if ev.button() == QtCore.Qt.RightButton:
            ev.accept()
            self.sigRightClicked.emit(self)
        else:
            super().mouseClickEvent(ev)

class OBBCurveItem(pg.PlotCurveItem):
    """PlotCurveItem subclass for OBB polygons.

    Intercepts right-click at the QGraphicsItem level (mouseClickEvent)
    and emits sigRightClicked �� identical pattern to AnnotationROI for BBox.
    Stores ann_index so the index can be updated in-place when annotations
    are removed, without stale lambda captures.
    """
    sigRightClicked = QtCore.pyqtSignal(object)

    def __init__(self, *args, ann_index: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.ann_index = ann_index
        # PlotCurveItem does not accept mouse events by default �� enable it.
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton | QtCore.Qt.RightButton)

    def mouseClickEvent(self, ev) -> None:
        if ev.button() == QtCore.Qt.RightButton:
            ev.accept()
            self.sigRightClicked.emit(self)
        else:
            super().mouseClickEvent(ev)

class PolylineItem(pg.PlotCurveItem):
    """PlotCurveItem subclass for LINE and KP skeleton connectors.

    Intercepts right-click and emits sigRightClicked with ann_index,
    following the same pattern as AnnotationROI (BBox) and OBBCurveItem.
    """
    sigRightClicked = QtCore.pyqtSignal(object)

    def __init__(self, *args, ann_index: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.ann_index = ann_index
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton | QtCore.Qt.RightButton)

    def mouseClickEvent(self, ev) -> None:
        if ev.button() == QtCore.Qt.RightButton:
            ev.accept()
            self.sigRightClicked.emit(self)
        else:
            super().mouseClickEvent(ev)

class ScatterAnnotItem(pg.ScatterPlotItem):
    """ScatterPlotItem subclass for KP and LINE vertex dots.

    Intercepts right-click and emits sigRightClicked with ann_index.
    ScatterPlotItem already accepts mouse events, but we need to intercept
    right-click before pyqtgraph shows its own menu.
    """
    sigRightClicked = QtCore.pyqtSignal(object)

    def __init__(self, *args, ann_index: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.ann_index = ann_index

    def mouseClickEvent(self, ev) -> None:
        if ev.button() == QtCore.Qt.RightButton:
            ev.accept()
            self.sigRightClicked.emit(self)
        else:
            super().mouseClickEvent(ev)


class AnnotationCanvas(QtCore.QObject):
    """Drawing/edit overlay; image reloads never replace canonical geometry."""
    bbox_drawn = QtCore.pyqtSignal(float, float, float, float)
    kp_drawn = QtCore.pyqtSignal(list, list)
    line_drawn = QtCore.pyqtSignal(list, list)
    shape_drawn = QtCore.pyqtSignal(str, list)
    shape_edited = QtCore.pyqtSignal(int, str, list)
    edit_requested = QtCore.pyqtSignal(int)
    selected = QtCore.pyqtSignal(int)
    remove_requested = QtCore.pyqtSignal(int)
    state_changed = QtCore.pyqtSignal(str)
    message = QtCore.pyqtSignal(str)

    def __init__(self, plot_widget, parent=None):
        super().__init__(parent)
        self.plot_widget = plot_widget
        self._ann_type = AnnType.BBOX
        self._annotation_mode = False
        self._drag_start = None
        self._drag_roi = None
        self._ann_pts_t = []
        self._ann_pts_d = []
        self._live_items = []
        self._display_items = []
        self._ann_geoms = {}
        self._edit_items = []
        self._edit_id = None
        self._edit_type = None
        self._edit_points = []
        self._updating_handles = False
        self.bounds = None
        self._vline = pg.InfiniteLine(angle=90, pen=pg.mkPen("#667085", style=QtCore.Qt.DashLine))
        self._hline = pg.InfiniteLine(angle=0, pen=pg.mkPen("#667085", style=QtCore.Qt.DashLine))
        self.bbox_drawn.connect(self._bbox_completed)
        self.kp_drawn.connect(lambda xs, ys: self._complete("kp", list(zip(xs, ys))))
        self.line_drawn.connect(lambda xs, ys: self._complete("lin", list(zip(xs, ys))))
        plot_widget.scene().sigMouseClicked.connect(self._on_scene_clicked)
        plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)
        # This filter is scoped to this window and skips text editors.
        QtWidgets.QApplication.instance().installEventFilter(self)
        self._original_wheel = plot_widget.getViewBox().wheelEvent
        plot_widget.getViewBox().wheelEvent = self._wheel_event

    @property
    def busy(self):
        return self._annotation_mode or self._edit_id is not None

    def set_bounds(self, duration, channel_count):
        new = (float(duration), float(channel_count))
        if self.bounds != new and self.busy:
            self.cancel()
        self.bounds = new

    def _wheel_event(self, event, axis=None):
        vb = self.plot_widget.getViewBox()
        if self.busy:
            vb.setMouseEnabled(x=True, y=True)
        self._original_wheel(event, axis)
        if self.busy:
            vb.setMouseEnabled(x=False, y=False)

    def set_mode(self, kind):
        self.cancel()
        if not kind:
            return
        if self.bounds is None:
            self.message.emit("请先导入 DAS 数据")
            return
        self._ann_type = AnnType(kind)
        self._annotation_mode = True
        self.plot_widget.getViewBox().setMouseEnabled(x=False, y=False)
        self.plot_widget.setCursor(QtCore.Qt.CrossCursor)
        self._attach(self._vline)
        self._attach(self._hline)
        self.state_changed.emit(kind)
        instructions = {
            "bbox": "事件框：依次点击两个对角；Esc 取消",
            "obb": "倾斜框：点击长轴两端，再点击宽度位置；Esc 取消",
            "kp": "关键点：逐点点击，Enter / 双击完成；Backspace 撤销节点",
            "lin": "轨迹线：沿轨迹逐点点击，Enter / 双击完成；Backspace 撤销节点",
        }
        self.message.emit(instructions[kind])

    def _attach(self, item):
        if item.scene() is None:
            self.plot_widget.addItem(item)
        item.setZValue(65)

    def _remove(self, item):
        if item.scene() is not None:
            self.plot_widget.removeItem(item)

    def _cancel_annotation(self):
        if self._drag_roi is not None:
            self._remove(self._drag_roi)
            self._drag_roi = None
        for item in self._live_items:
            self._remove(item)
        self._live_items.clear()
        self._ann_pts_t.clear()
        self._ann_pts_d.clear()
        self._drag_start = None

    def cancel(self):
        self._cancel_annotation()
        for item in self._edit_items:
            self._remove(item)
        self._edit_items.clear()
        self._edit_id = None
        self._edit_type = None
        self._edit_points = []
        self._annotation_mode = False
        self._remove(self._vline)
        self._remove(self._hline)
        self.plot_widget.setCursor(QtCore.Qt.ArrowCursor)
        self.plot_widget.getViewBox().setMouseEnabled(x=True, y=True)
        self.state_changed.emit("")

    def _in_bounds(self, t, d):
        return self.bounds is not None and 0 <= t <= self.bounds[0] and 0 <= d <= self.bounds[1]

    def _on_scene_clicked(self, event):
        if event.button() == QtCore.Qt.RightButton and event.isAccepted():
            # A shape item's right-click signal already opened its menu.
            return
        vb = self.plot_widget.getViewBox()
        if not vb.sceneBoundingRect().contains(event.scenePos()):
            return
        pos = vb.mapSceneToView(event.scenePos())
        t, d = pos.x(), pos.y()
        if self.busy:
            if event.button() == QtCore.Qt.RightButton:
                event.accept()
                self.cancel()
                return
            if self._edit_id is not None:
                return
            if event.button() != QtCore.Qt.LeftButton or not self._in_bounds(t, d):
                return
            event.accept()
            if self._ann_type == AnnType.BBOX:
                self._handle_click_bbox(t, d)
            elif self._ann_type == AnnType.OBB:
                self._handle_click_obb(t, d)
            else:
                self._handle_click_multipoint(t, d, event)
            return
        identifier = self._hit_test(event.scenePos())
        if identifier is None:
            return
        if event.button() == QtCore.Qt.RightButton:
            event.accept()
            self._show_context_menu(identifier)
        elif event.button() == QtCore.Qt.LeftButton:
            event.accept()
            self.selected.emit(identifier)

    def _on_mouse_moved(self, scene_pos):
        if not self._annotation_mode:
            return
        pos = self.plot_widget.getViewBox().mapSceneToView(scene_pos)
        t, d = pos.x(), pos.y()
        self._vline.setPos(t)
        self._hline.setPos(d)
        if self._ann_type == AnnType.BBOX and self._drag_roi is not None:
            t0, d0 = self._drag_start
            self._drag_roi.setPos([min(t0, t), min(d0, d)])
            self._drag_roi.setSize([abs(t-t0), abs(d-d0)])
        elif self._ann_type == AnnType.OBB and self._ann_pts_t:
            for item in self._live_items:
                self._remove(item)
            self._live_items.clear()
            fixed = list(zip(self._ann_pts_t, self._ann_pts_d))
            points = fixed + [(t, d)] if len(fixed) == 1 else self._obb_corners(fixed + [(t, d)])
            if points:
                if len(fixed) == 2:
                    points = points + [points[0]]
                preview = pg.PlotCurveItem(*np.asarray(points).T, pen=_ANN_TYPE_PENS[AnnType.OBB]())
                self._attach(preview)
                self._live_items.append(preview)

    def _bbox_completed(self, t0, t1, d0, d1):
        self._complete("bbox", [(t0,d0), (t1,d0), (t1,d1), (t0,d1)])

    def _complete(self, kind, points):
        self.cancel()
        self.shape_drawn.emit(kind, [list(point) for point in points])

    def _obb_corners(self, controls):
        # Borrow DASexplorer's screen-normalised three-click workflow, mapping
        # all four corners back to data units instead of mixing seconds/metres.
        vb = self.plot_widget.getViewBox()
        p1, p2, pc = [vb.mapViewToScene(pg.Point(*p)) for p in controls]
        a = np.array([p1.x(), p1.y()])
        b = np.array([p2.x(), p2.y()])
        width_point = np.array([pc.x(), pc.y()])
        axis = b-a
        length = np.linalg.norm(axis)
        if length < 1:
            return []
        normal = np.array([-axis[1], axis[0]]) / length
        half_width = max(1.0, abs(np.dot(width_point-a, normal)))
        corners = [a+normal*half_width, b+normal*half_width,
                   b-normal*half_width, a-normal*half_width]
        result = []
        for corner in corners:
            point = vb.mapSceneToView(pg.Point(*corner))
            result.append([point.x(), point.y()])
        return result

    def _handle_click_obb(self, t, d):
        if len(self._ann_pts_t) < 2:
            self._ann_pts_t.append(t)
            self._ann_pts_d.append(d)
        else:
            points = self._obb_corners(list(zip(self._ann_pts_t, self._ann_pts_d)) + [(t,d)])
            if points:
                self._complete("obb", points)

    def _hit_test(self, scene_pos):
        # Screen-pixel hit threshold stays usable at every zoom level.
        vb = self.plot_widget.getViewBox()
        pointer = np.array([scene_pos.x(), scene_pos.y()])
        best, best_distance = None, 12.0
        for identifier, (kind, points) in reversed(list(self._ann_geoms.items())):
            screen = [vb.mapViewToScene(pg.Point(*p)) for p in points]
            if kind in ("bbox", "obb", "interval"):
                polygon = QtGui.QPolygonF(screen)
                if polygon.containsPoint(scene_pos, QtCore.Qt.OddEvenFill):
                    return identifier
            coords = [np.array([p.x(), p.y()]) for p in screen]
            for p in coords:
                distance = np.linalg.norm(pointer-p)
                if distance < best_distance:
                    best, best_distance = identifier, distance
            edges = list(zip(coords, coords[1:]))
            if kind in ("bbox", "obb") and coords:
                edges.append((coords[-1], coords[0]))
            for a, b in edges:
                direction = b-a
                ratio = np.clip(np.dot(pointer-a, direction) / max(np.dot(direction,direction), 1e-12), 0, 1)
                distance = np.linalg.norm(pointer-(a+ratio*direction))
                if distance < best_distance:
                    best, best_distance = identifier, distance
        return best

    def _show_context_menu(self, identifier):
        if self.busy:
            return
        menu = QtWidgets.QMenu(self.plot_widget)
        edit = menu.addAction("编辑属性")
        shape = menu.addAction("编辑形状")
        shape.setEnabled(self._ann_geoms.get(identifier, (None,))[0] in TYPE_LABELS)
        remove = menu.addAction("删除标注")
        chosen = menu.exec_(QtGui.QCursor.pos())
        if chosen == edit:
            self.edit_requested.emit(identifier)
        elif chosen == shape:
            self.start_edit(identifier)
        elif chosen == remove:
            self.remove_requested.emit(identifier)

    def clear_rendered(self):
        for item in self._display_items:
            self._remove(item)
        self._display_items.clear()
        self._ann_geoms.clear()

    def render_shape(self, identifier, kind, points, label, selected=False, tooltip=""):
        self._ann_geoms[identifier] = (kind, points)
        color = "#2563eb" if selected else COLORS[kind]
        pen = pg.mkPen(color, width=3 if selected else 2)
        xs, ys = np.asarray(points, dtype=float).T
        items = []
        if kind == "bbox":
            roi = AnnotationROI([min(xs),min(ys)], [max(xs)-min(xs),max(ys)-min(ys)],
                                ann_index=identifier, pen=pen, movable=False)
            items.append(roi)
        elif kind == "obb":
            items.append(OBBCurveItem(list(xs)+[xs[0]], list(ys)+[ys[0]], pen=pen,
                                      ann_index=identifier))
        else:
            if kind == "lin":
                items.append(PolylineItem(xs, ys, pen=pen, ann_index=identifier))
            items.append(ScatterAnnotItem(xs, ys, pen=pen, brush=pg.mkBrush(color),
                                          size=10, ann_index=identifier))
        for item in items:
            item.setZValue(40)
            item.setToolTip(tooltip)
            item.sigRightClicked.connect(lambda it: self._show_context_menu(it.ann_index))
            self.plot_widget.addItem(item)
        text = pg.TextItem(label, color=color, anchor=(0,1), fill=pg.mkBrush(255,255,255,215))
        text.setPos(xs[0],ys[0])
        text.setZValue(41)
        text.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        self.plot_widget.addItem(text)
        self._display_items.extend(items+[text])

    def restore_overlays(self):
        # PlotWidget.clear() detaches overlays during asynchronous image loads.
        if self._annotation_mode:
            self._attach(self._vline)
            self._attach(self._hline)
            if self._drag_roi is not None:
                self._attach(self._drag_roi)
            for item in self._live_items:
                self._attach(item)
        for item in self._edit_items:
            self._attach(item)

    def start_edit(self, identifier):
        entry = self._ann_geoms.get(identifier)
        if entry is None:
            return
        kind, points = entry
        if kind not in TYPE_LABELS:
            return
        self.cancel()
        self._edit_id = identifier
        self._edit_type = kind
        if kind == "obb":
            p = np.asarray(points)
            self._edit_points = [((p[0]+p[3])/2).tolist(), ((p[1]+p[2])/2).tolist(),
                                 ((p[0]+p[1])/2).tolist()]
        else:
            self._edit_points = [list(p) for p in points]
        outline = pg.PlotCurveItem(pen=pg.mkPen("#f58231", width=2, style=QtCore.Qt.DashLine))
        self._edit_items = [outline]
        self._attach(outline)
        # Reuse DASexplorer's draggable TargetItem edit handles and connector.
        for index, point in enumerate(self._edit_points):
            target = pg.TargetItem(pos=point, size=14, symbol="o",
                                   pen=pg.mkPen("#ffffff"), brush=pg.mkBrush("#f58231"), movable=True)
            target.sigPositionChanged.connect(lambda item, i=index: self._handle_moved(i, item))
            self._attach(target)
            self._edit_items.append(target)
        self.plot_widget.getViewBox().setMouseEnabled(x=False,y=False)
        self._refresh_edit_outline()
        self.state_changed.emit("edit")
        self.message.emit("编辑形状：拖动橙色节点，Enter / 保存形状提交；Esc 取消")

    def _handle_moved(self, index, item):
        if self._updating_handles:
            return
        point = [item.pos().x(), item.pos().y()]
        if self.bounds:
            point = [float(np.clip(point[0],0,self.bounds[0])),
                     float(np.clip(point[1],0,self.bounds[1]))]
        if self._edit_type == "bbox":
            opposite = self._edit_points[(index+2)%4]
            t0,t1 = sorted([point[0],opposite[0]])
            d0,d1 = sorted([point[1],opposite[1]])
            self._edit_points = [[t0,d0],[t1,d0],[t1,d1],[t0,d1]]
        else:
            self._edit_points[index] = point
        self._refresh_edit_outline()

    def _edited_geometry(self):
        return self._obb_corners(self._edit_points) if self._edit_type == "obb" else self._edit_points

    def _refresh_edit_outline(self):
        points = self._edited_geometry()
        if points:
            closed = self._edit_type in ("bbox","obb")
            drawing_points = points+[points[0]] if closed else points
            self._edit_items[0].setData(*np.asarray(drawing_points).T)
        self._updating_handles = True
        try:
            for target, point in zip(self._edit_items[1:], self._edit_points):
                target.setPos(*point)
        finally:
            self._updating_handles = False

    def commit_edit(self):
        if self._edit_id is None:
            return
        points = self._edited_geometry()
        if not points or any(not self._in_bounds(*point) for point in points):
            self.message.emit("形状超出 DAS 范围，请将节点移回图内再保存")
            return
        identifier, kind = self._edit_id, self._edit_type
        self.cancel()
        self.shape_edited.emit(identifier, kind, [list(p) for p in points])

    def eventFilter(self, obj, event):
        if event.type() != QtCore.QEvent.KeyPress or not self.busy or not self.plot_widget.isVisible():
            return False
        if QtWidgets.QApplication.activeWindow() is not self.plot_widget.window():
            return False
        if any(obj.inherits(name) for name in ("QLineEdit","QAbstractSpinBox","QComboBox")):
            return False
        key = event.key()
        if key == QtCore.Qt.Key_Escape:
            self.cancel()
            return True
        if key in (QtCore.Qt.Key_Return,QtCore.Qt.Key_Enter):
            if self._edit_id is not None:
                self.commit_edit()
            elif self._ann_type in (AnnType.KP,AnnType.LINE):
                self._finalise_multipoint()
            return True
        if key == QtCore.Qt.Key_Backspace and self._annotation_mode:
            if self._ann_pts_t:
                self._ann_pts_t.pop()
                self._ann_pts_d.pop()
                # Rebuild multipoint preview after dropping the last vertex.
                for item in self._live_items:
                    self._remove(item)
                self._live_items.clear()
                if self._ann_pts_t:
                    xs,ys = self._ann_pts_t,self._ann_pts_d
                    preview = pg.PlotDataItem(xs,ys,pen=_ANN_TYPE_PENS[self._ann_type](),
                                             symbol="o",symbolBrush=COLORS[self._ann_type.value])
                    self._attach(preview)
                    self._live_items.append(preview)
            return True
        return False

    def _finalise_multipoint(self) -> None:
        """Emit the signal for KP or LINE once the user presses Enter."""
        if self._ann_type == AnnType.KP and len(self._ann_pts_t) >= 1:
            self.kp_drawn.emit(list(self._ann_pts_t), list(self._ann_pts_d))
        elif self._ann_type == AnnType.LINE and len(self._ann_pts_t) >= 2:
            self.line_drawn.emit(list(self._ann_pts_t), list(self._ann_pts_d))
        self._cancel_annotation()

    def _handle_click_bbox(self, t: float, d: float) -> None:
        if self._drag_start is None:
            self._drag_start = (t, d)
            self._drag_roi = pg.RectROI(
                [t, d], [0.001, 0.001],
                pen=_bbox_pen(), movable=False, resizable=False,
            )
            while self._drag_roi.handles:
                self._drag_roi.removeHandle(0)
            self.plot_widget.addItem(self._drag_roi)
            self._attach(self._drag_roi)
        else:
            t0, d0 = self._drag_start
            t1, d1 = t, d
            self._cancel_annotation()
            if abs(t1 - t0) > 1e-9 and abs(d1 - d0) > 0.01:
                self.bbox_drawn.emit(
                    min(t0, t1), max(t0, t1),
                    min(d0, d1), max(d0, d1),
                )

    def _handle_click_multipoint(self, t: float, d: float, event) -> None:
        is_double = (event.double() if hasattr(event, 'double') else False)

        if is_double and self._ann_pts_t and (t, d) == (self._ann_pts_t[-1], self._ann_pts_d[-1]):
            self._finalise_multipoint()
            return

        self._ann_pts_t.append(t)
        self._ann_pts_d.append(d)

        # Draw a dot at this point
        dot = pg.ScatterPlotItem(
            [t], [d],
            pen=_ANN_TYPE_PENS[self._ann_type](),
            brush=pg.mkBrush(color=(*_ANN_TYPE_PENS[self._ann_type]().color().getRgb()[:3], 180)),
            size=8, symbol='o',
        )
        self.plot_widget.addItem(dot)
        self._live_items.append(dot)

        # Draw a connecting line if more than one point
        if len(self._ann_pts_t) > 1:
            seg = pg.PlotCurveItem(
                self._ann_pts_t, self._ann_pts_d,
                pen=_ANN_TYPE_PENS[self._ann_type](),
            )
            self.plot_widget.addItem(seg)
            self._live_items.append(seg)

        # Double-click or Enter �� finalise
        if is_double:
            self._finalise_multipoint()
