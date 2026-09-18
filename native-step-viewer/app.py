import json
import math
import os
import sys
import traceback
from pathlib import Path

import numpy as np

APP_NAME = "CapsuleDesign STEP Viewer"
APP_VERSION = "0.3.1"

def _shape_list_from_step(path):
    import cadquery as cq
    obj = cq.importers.importStep(str(path))
    shapes = []
    for candidate in getattr(obj, "objects", []) or []:
        if hasattr(candidate, "tessellate") and hasattr(candidate, "BoundingBox"):
            shapes.append(candidate)
    if not shapes:
        value = obj.val()
        if value is not None:
            shapes = [value]
    return shapes

def _mesh_and_stats(path, linear_tol=None, angular_tol=0.15):
    shapes = _shape_list_from_step(path)
    if not shapes:
        raise RuntimeError("STEP/STP 파일에서 형상을 찾지 못했습니다.")

    all_meshes = []
    total_volume = 0.0
    total_area = 0.0
    xmin = ymin = zmin = float("inf")
    xmax = ymax = zmax = float("-inf")

    for index, shape in enumerate(shapes):
        bb = shape.BoundingBox()
        xmin = min(xmin, float(bb.xmin)); xmax = max(xmax, float(bb.xmax))
        ymin = min(ymin, float(bb.ymin)); ymax = max(ymax, float(bb.ymax))
        zmin = min(zmin, float(bb.zmin)); zmax = max(zmax, float(bb.zmax))

        try:
            total_volume += abs(float(shape.Volume()))
        except Exception:
            pass
        try:
            total_area += float(shape.Area())
        except Exception:
            pass

        local_tol = linear_tol
        if local_tol is None:
            diag = math.sqrt(float(bb.xlen) ** 2 + float(bb.ylen) ** 2 + float(bb.zlen) ** 2)
            local_tol = max(0.03, min(0.35, diag / 900.0))

        vertices, triangles = shape.tessellate(float(local_tol), float(angular_tol))
        verts = np.asarray([[float(v.x), float(v.y), float(v.z)] for v in vertices], dtype=np.float32)
        faces = np.asarray(triangles, dtype=np.uint32)
        if len(verts) and len(faces):
            # STEP의 실제 B-Rep 모서리만 별도로 샘플링한다.
            # 삼각분할 mesh의 내부 edge는 표시하지 않는다.
            edge_segments = []
            edge_deflection = max(0.02, min(0.12, local_tol * 0.55))
            try:
                for edge in shape.Edges():
                    try:
                        pts, _ = edge.sample(float(edge_deflection))
                    except Exception:
                        pts = [edge.startPoint(), edge.endPoint()]
                    if len(pts) < 2:
                        continue
                    for a, b in zip(pts[:-1], pts[1:]):
                        edge_segments.append(
                            [
                                [float(a.x), float(a.y), float(a.z)],
                                [float(b.x), float(b.y), float(b.z)],
                            ]
                        )
                    if edge.IsClosed() and len(pts) > 2:
                        a, b = pts[-1], pts[0]
                        edge_segments.append(
                            [
                                [float(a.x), float(a.y), float(a.z)],
                                [float(b.x), float(b.y), float(b.z)],
                            ]
                        )
            except Exception:
                edge_segments = []

            edges_np = (
                np.asarray(edge_segments, dtype=np.float32).reshape(-1, 3)
                if edge_segments
                else np.empty((0, 3), dtype=np.float32)
            )
            all_meshes.append((f"Body {index + 1}", verts, faces, edges_np))

    if not all_meshes:
        raise RuntimeError("형상은 읽었지만 화면에 표시할 삼각망을 만들지 못했습니다.")

    return {
        "meshes": all_meshes,
        "body_count": len(all_meshes),
        "triangle_count": int(sum(len(f) for _, _, f, _ in all_meshes)),
        "volume_mm3": total_volume,
        "area_mm2": total_area,
        "bounds": (xmin, xmax, ymin, ymax, zmin, zmax),
        "size": (xmax - xmin, ymax - ymin, zmax - zmin),
        "center": ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0, (zmin + zmax) / 2.0),
    }

def run_selftest(step_path):
    data = _mesh_and_stats(step_path)
    print(json.dumps({
        "ok": True,
        "version": APP_VERSION,
        "file": str(step_path),
        "bodies": data["body_count"],
        "triangles": data["triangle_count"],
        "volume_mm3": round(data["volume_mm3"], 6),
        "area_mm2": round(data["area_mm2"], 6),
        "size_mm": [round(v, 6) for v in data["size"]],
    }, ensure_ascii=False))
    return 0

def gui_main():
    from PySide6 import QtCore, QtGui, QtWidgets
    import pyqtgraph as pg
    import pyqtgraph.opengl as gl
    from pyqtgraph.opengl.shaders import ShaderProgram, VertexShader, FragmentShader

    pg.setConfigOptions(antialias=True)

    # CAD 뷰어용 밝은 양면 조명 셰이더.
    # 기본 pyqtgraph 'shaded'는 암부가 20%까지 떨어져 금형 형상이 지나치게 어둡게 보인다.
    ShaderProgram('cadBright', [
        VertexShader("""
            varying vec3 normal;
            void main() {
                normal = normalize(gl_NormalMatrix * gl_Normal);
                gl_FrontColor = gl_Color;
                gl_BackColor = gl_Color;
                gl_Position = ftransform();
            }
        """),
        FragmentShader("""
            varying vec3 normal;
            void main() {
                vec3 n = normalize(normal);
                vec3 l1 = normalize(vec3(0.70, -0.45, 0.72));
                vec3 l2 = normalize(vec3(-0.60, 0.35, 0.78));
                float d1 = abs(dot(n, l1));
                float d2 = abs(dot(n, l2));
                float rim = pow(1.0 - abs(n.z), 2.0);
                float light = clamp(0.58 + 0.27*d1 + 0.16*d2 + 0.06*rim, 0.58, 1.04);
                vec4 color = gl_Color;
                color.rgb = clamp(color.rgb * light, 0.0, 1.0);
                gl_FragColor = color;
            }
        """)
    ])

    class Viewer(gl.GLViewWidget):
        fileDropped = QtCore.Signal(str)

        def __init__(self):
            super().__init__()
            self.setAcceptDrops(True)
            self.setBackgroundColor((6, 8, 10, 255))
            self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        def dragEnterEvent(self, event):
            urls = event.mimeData().urls()
            if urls:
                p = urls[0].toLocalFile().lower()
                if p.endswith((".stp", ".step")):
                    event.acceptProposedAction()
                    return
            super().dragEnterEvent(event)

        def dropEvent(self, event):
            urls = event.mimeData().urls()
            if urls:
                p = urls[0].toLocalFile()
                if p.lower().endswith((".stp", ".step")):
                    self.fileDropped.emit(p)
                    event.acceptProposedAction()
                    return
            super().dropEvent(event)

    class InfoPanel(QtWidgets.QFrame):
        def __init__(self):
            super().__init__()
            self.setObjectName("InfoPanel")
            self.setFixedWidth(292)
            lay = QtWidgets.QVBoxLayout(self)
            lay.setContentsMargins(18, 18, 18, 18)
            lay.setSpacing(10)

            title = QtWidgets.QLabel("모델 정보")
            title.setObjectName("PanelTitle")
            lay.addWidget(title)

            self.rows = {}
            for key, label in [
                ("dims", "치수"),
                ("bodies", "바디"),
                ("tris", "삼각형"),
                ("volume", "부피"),
                ("area", "표면적"),
                ("unit", "단위"),
            ]:
                row = QtWidgets.QHBoxLayout()
                left = QtWidgets.QLabel(label)
                left.setObjectName("Muted")
                right = QtWidgets.QLabel("-" if key != "unit" else "mm")
                right.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                right.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
                row.addWidget(left)
                row.addStretch(1)
                row.addWidget(right)
                lay.addLayout(row)
                self.rows[key] = right

            line = QtWidgets.QFrame()
            line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
            line.setObjectName("Sep")
            lay.addWidget(line)

            local = QtWidgets.QLabel("✓  로컬 PC에서 STEP 형상을 해석합니다.\n브라우저나 127.0.0.1 서버를 사용하지 않습니다.")
            local.setWordWrap(True)
            local.setObjectName("LocalNote")
            lay.addWidget(local)
            lay.addStretch(1)

        def clear(self):
            for k, v in self.rows.items():
                v.setText("mm" if k == "unit" else "-")

        def set_stats(self, data):
            sx, sy, sz = data["size"]
            self.rows["dims"].setText(f"{sx:.2f} × {sy:.2f} × {sz:.2f} mm")
            self.rows["bodies"].setText(f"{data['body_count']:,}")
            self.rows["tris"].setText(f"{data['triangle_count']:,}")
            self.rows["volume"].setText(f"{data['volume_mm3'] / 1000.0:,.2f} cm³")
            self.rows["area"].setText(f"{data['area_mm2'] / 100.0:,.2f} cm²")

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
            self.resize(1500, 900)
            self.setMinimumSize(980, 640)
            self.mesh_items = []
            self.edge_items = []
            self.model_data = None
            self.current_path = None

            root = QtWidgets.QWidget()
            self.setCentralWidget(root)
            outer = QtWidgets.QVBoxLayout(root)
            outer.setContentsMargins(14, 12, 14, 14)
            outer.setSpacing(10)

            top = QtWidgets.QHBoxLayout()
            brand = QtWidgets.QLabel(APP_NAME)
            brand.setObjectName("Brand")
            top.addWidget(brand)

            self.file_label = QtWidgets.QLabel("STEP/STP 파일을 여세요")
            self.file_label.setObjectName("FileChip")
            self.file_label.setMinimumWidth(280)
            self.file_label.setMaximumWidth(520)
            top.addWidget(self.file_label)

            self.open_btn = QtWidgets.QPushButton("파일 열기")
            self.open_btn.setObjectName("Primary")
            self.open_btn.clicked.connect(self.open_file_dialog)
            top.addWidget(self.open_btn)

            fit_btn = QtWidgets.QPushButton("화면 맞춤")
            fit_btn.clicked.connect(lambda: self.set_view("iso"))
            top.addWidget(fit_btn)
            top.addStretch(1)

            ver = QtWidgets.QLabel(f"Native Qt / OCCT  v{APP_VERSION}")
            ver.setObjectName("Version")
            top.addWidget(ver)
            outer.addLayout(top)

            content = QtWidgets.QHBoxLayout()
            content.setSpacing(12)
            self.info = InfoPanel()
            content.addWidget(self.info)

            self.viewer = Viewer()
            self.viewer.fileDropped.connect(self.load_step)
            content.addWidget(self.viewer, 1)

            toolbar = QtWidgets.QFrame()
            toolbar.setObjectName("ToolBar")
            toolbar.setFixedWidth(66)
            tlay = QtWidgets.QVBoxLayout(toolbar)
            tlay.setContentsMargins(8, 10, 8, 10)
            tlay.setSpacing(7)

            def add_tool(text, tip, slot, checkable=False):
                b = QtWidgets.QPushButton(text)
                b.setProperty("toolButton", True)
                b.setToolTip(tip)
                b.setFixedSize(48, 42)
                b.setCheckable(checkable)
                b.clicked.connect(slot)
                tlay.addWidget(b)
                return b

            add_tool("+", "확대", lambda: self.zoom(0.82))
            add_tool("−", "축소", lambda: self.zoom(1.22))
            add_tool("◎", "화면 맞춤", lambda: self.set_view("iso"))
            self.iso_btn = add_tool("◇", "등각뷰", lambda: self.set_view("iso"), True)
            add_tool("T", "평면", lambda: self.set_view("top"))
            add_tool("F", "정면", lambda: self.set_view("front"))
            add_tool("R", "우측면", lambda: self.set_view("right"))
            self.edge_btn = add_tool("▦", "외곽선", self.toggle_edges, True)
            self.edge_btn.setChecked(True)
            self.face_btn = add_tool("▣", "면 표시", self.toggle_faces, True)
            self.face_btn.setChecked(True)
            tlay.addStretch(1)
            shot = add_tool("PNG", "현재 화면 저장", self.save_screenshot)
            shot.setStyleSheet("font-size:10px;")
            content.addWidget(toolbar)
            outer.addLayout(content, 1)

            self.empty_label = QtWidgets.QLabel("STEP / STP 파일을 끌어놓거나 ‘파일 열기’를 누르세요\n"
                                                "회전: 왼쪽 드래그  ·  이동: Ctrl+왼쪽 드래그  ·  확대: 휠")
            self.empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.empty_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.empty_label.setObjectName("EmptyHint")
            self.empty_label.setParent(self.viewer)
            self.empty_label.show()

            self.statusBar().showMessage("준비")

            # 기본 격자 평면은 모델을 가려서 표시하지 않는다.
            self.apply_style()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if hasattr(self, "empty_label"):
                self.empty_label.setGeometry(self.viewer.rect())

        def apply_style(self):
            self.setStyleSheet("""
            QMainWindow, QWidget { background:#080a0c; color:#edf1f4; font-family:'Segoe UI','Malgun Gothic'; font-size:13px; }
            #Brand { font-size:16px; font-weight:700; padding:0 8px 0 2px; }
            #FileChip { background:#15191d; border:1px solid #363d44; border-radius:10px; padding:9px 12px; color:#d8dee2; }
            QPushButton { background:#171b1f; border:1px solid #384047; border-radius:9px; padding:9px 13px; font-weight:600; }
            QPushButton:hover { background:#242a2f; }
            QPushButton:pressed { background:#30373d; }
            QPushButton:checked { background:#a8ff2e; color:#132000; border-color:#a8ff2e; }
            #Primary { background:#a8ff2e; color:#132000; border-color:#a8ff2e; }
            #InfoPanel, #ToolBar { background:#111519; border:1px solid #363e45; border-radius:14px; }
            #PanelTitle { font-size:14px; font-weight:700; color:#c7cfd4; }
            #Muted { color:#87939b; }
            #LocalNote { color:#9aa6ad; font-size:12px; line-height:1.4; }
            #Sep { color:#31383e; background:#31383e; max-height:1px; }
            #Version { color:#69757d; font-size:11px; }
            #EmptyHint { color:#818c94; background:transparent; font-size:14px; }
            QStatusBar { background:#0e1114; color:#8d989f; }
            """)

        def open_file_dialog(self):
            p, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "STEP/STP 파일 열기", str(Path.home()),
                "STEP CAD (*.stp *.step);;모든 파일 (*.*)"
            )
            if p:
                self.load_step(p)

        def clear_model(self):
            for item in self.mesh_items + self.edge_items:
                try:
                    self.viewer.removeItem(item)
                except Exception:
                    pass
            self.mesh_items.clear()
            self.edge_items.clear()
            self.model_data = None

        def load_step(self, path):
            path = str(path)
            if not path.lower().endswith((".stp", ".step")):
                QtWidgets.QMessageBox.warning(self, APP_NAME, "STP 또는 STEP 파일만 지원합니다.")
                return

            self.statusBar().showMessage("STEP 형상 해석 중...")
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            try:
                data = _mesh_and_stats(path)
                self.clear_model()

                # 밝은 CAD 실버 톤. 곡면 음영은 cadBright 셰이더가 담당한다.
                face_color = (0.90, 0.92, 0.99, 1.0)
                edge_color = (0.32, 0.37, 0.48, 0.62)

                for name, verts, faces, edge_segments in data["meshes"]:
                    md = gl.MeshData(vertexes=verts, faces=faces)

                    face = gl.GLMeshItem(
                        meshdata=md, smooth=True,
                        color=face_color, shader="cadBright",
                        drawEdges=False, drawFaces=True
                    )
                    face.setGLOptions("opaque")
                    self.viewer.addItem(face)
                    self.mesh_items.append(face)

                    # 삼각분할 선이 아니라 STEP 원본의 실제 B-Rep 모서리만 표시한다.
                    if len(edge_segments):
                        edge = gl.GLLinePlotItem(
                            pos=edge_segments,
                            color=edge_color,
                            width=1.05,
                            antialias=True,
                            mode="lines",
                        )
                        edge.setGLOptions("translucent")
                        self.viewer.addItem(edge)
                        self.edge_items.append(edge)

                self.model_data = data
                self.current_path = path
                self.file_label.setText(Path(path).name)
                self.file_label.setToolTip(path)
                self.info.set_stats(data)
                self.empty_label.hide()
                self.set_view("iso")
                self.statusBar().showMessage(
                    f"불러오기 완료  |  바디 {data['body_count']}  |  삼각형 {data['triangle_count']:,}"
                )
            except Exception as exc:
                self.statusBar().showMessage("불러오기 실패")
                detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                QtWidgets.QMessageBox.critical(self, APP_NAME, f"STEP 파일을 열지 못했습니다.\n\n{detail}")
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()

        def set_view(self, mode):
            if not self.model_data:
                return
            cx, cy, cz = self.model_data["center"]
            sx, sy, sz = self.model_data["size"]
            maxdim = max(sx, sy, sz, 1.0)
            self.viewer.opts["center"] = QtGui.QVector3D(float(cx), float(cy), float(cz))
            self.viewer.opts["distance"] = float(maxdim * 2.1)
            if mode == "top":
                self.viewer.opts["elevation"] = 89.9
                self.viewer.opts["azimuth"] = -90.0
            elif mode == "front":
                self.viewer.opts["elevation"] = 0.0
                self.viewer.opts["azimuth"] = -90.0
            elif mode == "right":
                self.viewer.opts["elevation"] = 0.0
                self.viewer.opts["azimuth"] = 0.0
            else:
                self.viewer.opts["elevation"] = 28.0
                self.viewer.opts["azimuth"] = -45.0
            self.viewer.update()

        def zoom(self, factor):
            try:
                self.viewer.opts["distance"] = max(0.01, float(self.viewer.opts["distance"]) * factor)
                self.viewer.update()
            except Exception:
                pass

        def toggle_edges(self):
            visible = self.edge_btn.isChecked()
            for item in self.edge_items:
                item.setVisible(visible)

        def toggle_faces(self):
            visible = self.face_btn.isChecked()
            for item in self.mesh_items:
                item.setVisible(visible)

        def save_screenshot(self):
            if not self.current_path:
                return
            default = str(Path(self.current_path).with_suffix("")) + "_viewer.png"
            p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "화면 저장", default, "PNG 이미지 (*.png)")
            if p:
                img = self.viewer.grabFramebuffer()
                if img.save(p, "PNG"):
                    self.statusBar().showMessage(f"저장됨: {p}", 4000)
                else:
                    QtWidgets.QMessageBox.warning(self, APP_NAME, "PNG 저장에 실패했습니다.")

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    win = MainWindow()
    win.showMaximized()

    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file() and sys.argv[1].lower().endswith((".stp", ".step")):
        QtCore.QTimer.singleShot(300, lambda: win.load_step(sys.argv[1]))

    return app.exec()

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        sys.exit(run_selftest(sys.argv[2]))
    sys.exit(gui_main())
