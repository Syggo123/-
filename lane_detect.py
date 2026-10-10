"""
車道線偵測 + 中心偏移 CTE（Raspberry Pi 5 / PiCamera2）

流程（講義 p.15、p.16）：
  1. 影像讀取
  2. 前處理
       gray  模式：灰階 → 高斯模糊 → Canny          （講義原始流程）
       white 模式：灰階 → 亮度門檻 → 形態學 → Canny  （木地板 + 白膠帶，擋掉木紋）
       hsv   模式：HSV 顏色過濾 → 形態學 → Canny     （棕色 / 咖啡色膠帶）
       tophat 模式（預設）：灰階 → 白色 top-hat → 門檻 → 形態學 → 長且厚的區塊 → Canny
                     只留「比周圍亮的細長帶」：木板縫（暗線）、大片反光、牆面都會被擋掉
  3. Canny 邊緣檢測
  4. ROI 遮罩（只看畫面下半部梯形）
  5. 霍夫變換 HoughLinesP（邊緣像素 → 線段）
  6. 左右車道線擬合 + 中心線
       雙線：x0(y) = (xL(y) + xR(y)) / 2，順便更新 delta_x = xR - x0
       單線（只有右線）：x0(y) = xR(y) - delta_x      （講義 p.20）
       單線（只有左線）：x0(y) = xL(y) + delta_x
  7. CTE(y) = xc - x0(y)，xc = frame_width / 2
       CTE > 0 → 車子偏右；CTE < 0 → 車子偏左     （講義 p.18、p.21）
  8. 畫出結果 + FPS + 時間戳，存成影片

用法：
  python3 lane_detect.py                         # PiCamera 即時，錄 20 秒存 lane_output.mp4
  python3 lane_detect.py --mode white            # 木地板白膠帶（推薦）
  python3 lane_detect.py --mode hsv              # 棕色膠帶
  python3 lane_detect.py --debug                 # 錄影時每 2 秒存一張步驟拼圖到 debug/
  python3 lane_detect.py --image road.jpg        # 單張圖片測試
  python3 lane_detect.py --video in.mp4          # 用錄好的影片測試
  python3 lane_detect.py --show                  # 有螢幕時即時顯示視窗（SSH 不要加）
"""
import argparse
import time

import cv2
import numpy as np

# ---------------- 參數（依現場光線調整） ----------------
WIDTH, HEIGHT = 640, 480
CANNY_LOW, CANNY_HIGH = 20, 60      # 實拍淺色木地板：50/150 幾乎抓不到，20/60 剛好

# tophat 模式：kernel 要比畫面中最寬的膠帶還寬（車子正前方的膠帶最寬）
#   太小 → 近處膠帶被當成大片亮區濾掉；太大 → 反光條紋跑進來。實拍 27 張測下來 81 最平衡
TOPHAT_K = 81
TOPHAT_THRESH = 30       # top-hat 後亮度差超過這個才算膠帶
BLOB_MIN_LEN = 80        # 區塊的對角線長度下限（px）
BLOB_MIN_THICK = 8       # 區塊平均厚度下限 = 面積 / 對角線（反光是細條紋，膠帶是實心寬帶）

# white 模式：灰階值高於這個就算白膠帶（0-255）。抓不到膠帶就調低，木紋跑進來就調高
WHITE_THRESH = 170

# 棕色 / 咖啡色膠帶的 HSV 範圍（OpenCV: H 0-179, S 0-255, V 0-255）
HSV_LOWER = np.array([5, 80, 40])
HSV_UPPER = np.array([25, 255, 220])

# ROI：畫面下方梯形，數值是相對於寬高的比例
ROI_TOP_Y = 0.5            # 牆、家具在上半部，只看下半部地面
ROI_TOP_LEFT_X, ROI_TOP_RIGHT_X = 0.10, 0.90

# 長邊過濾：只保留外框長或寬 >= 這個像素的邊緣（膠帶邊是長線，地板反光的木紋是短碎線）
# 設成 0 就是關掉
MIN_EDGE_LEN = 120

# 霍夫變換
HOUGH_THRESHOLD = 30
HOUGH_MIN_LEN = 30
HOUGH_MAX_GAP = 40
MIN_ABS_SLOPE = 0.3          # 太水平的線段（例如地磚縫）丟掉

# 單線時用的「右線到中心線距離」delta_x(y)，講義 p.14「預先量測」、p.17
# 透視效果：越靠近畫面下方距離越大，所以分別給底部和 ROI 頂端的值，中間線性內插
DELTA_X_BOTTOM = 0.435 * WIDTH  # 10/07 第二批實測（14 張有效雙線的中位數，約 278px）
DELTA_X_TOP = 0.110 * WIDTH     # 同上（約 71px）。鏡頭角度一變這兩個值就要重算：python3 calibrate.py double_*.jpg
DELTA_SMOOTH = 0.1           # 看到雙線時，用 EMA 慢慢校正 delta_x(y)


def preprocess(frame, mode):
    """回傳 (邊緣圖, 中間結果)。"""
    if mode == "hsv":
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, HSV_LOWER, HSV_UPPER)
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)    # 侵蝕→膨脹：去雜訊
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)   # 膨脹→侵蝕：補縫隙
        edges = cv2.Canny(mask, CANNY_LOW, CANNY_HIGH)
        return edges, mask
    if mode == "tophat":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (TOPHAT_K, TOPHAT_K))
        tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)   # 原圖 - 開運算 = 比周圍亮的細東西
        _, mask = cv2.threshold(tophat, TOPHAT_THRESH, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = keep_thick_blobs(mask)
        edges = cv2.Canny(mask, CANNY_LOW, CANNY_HIGH)
        return edges, mask
    if mode == "white":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, mask = cv2.threshold(blur, WHITE_THRESH, 255, cv2.THRESH_BINARY)
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        edges = cv2.Canny(mask, CANNY_LOW, CANNY_HIGH)
        return edges, mask
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, CANNY_LOW, CANNY_HIGH)
    return edges, gray


def keep_thick_blobs(mask, min_len=None, min_thick=None):
    """只留又長又厚的白色區塊（膠帶），丟掉細條紋（反光）和小塊雜訊。"""
    min_len = BLOB_MIN_LEN if min_len is None else min_len
    min_thick = BLOB_MIN_THICK if min_thick is None else min_thick
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    w = stats[:, cv2.CC_STAT_WIDTH].astype(float)
    h = stats[:, cv2.CC_STAT_HEIGHT].astype(float)
    area = stats[:, cv2.CC_STAT_AREA].astype(float)
    diag = np.hypot(w, h) + 1e-6
    keep = (diag >= min_len) & (area / diag >= min_thick)
    keep[0] = False
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def keep_long_edges(edges, min_len=None):
    """連通元件分析：把太短的邊緣（反光、木紋）丟掉。"""
    if min_len is None:
        min_len = MIN_EDGE_LEN
    if min_len <= 0:
        return edges
    n, labels, stats, _ = cv2.connectedComponentsWithStats(edges, connectivity=8)
    keep = np.zeros(n, dtype=bool)
    keep[1:] = np.maximum(stats[1:, cv2.CC_STAT_WIDTH], stats[1:, cv2.CC_STAT_HEIGHT]) >= min_len
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def roi_mask(edges):
    h, w = edges.shape
    # 矩形 ROI：只看 ROI_TOP_Y 以下的地面。不用梯形，因為彎道時膠帶常貼著畫面左右邊緣，梯形斜邊會切掉
    poly = np.array([[(0, h), (0, int(h * ROI_TOP_Y)), (w, int(h * ROI_TOP_Y)), (w, h)]], dtype=np.int32)
    mask = np.zeros_like(edges)
    cv2.fillPoly(mask, poly, 255)
    return cv2.bitwise_and(edges, mask), poly


def fit_lanes(segments, w):
    """把霍夫線段分成左右兩群，各自擬合 x = a*y + b（車道線接近垂直，用 y 當自變數比較穩）。"""
    left_pts, right_pts = [], []
    if segments is None:
        return None, None
    for x1, y1, x2, y2 in segments.reshape(-1, 4):   # OpenCV 4 是 (N,1,4)、OpenCV 5 是 (N,4)
        if x1 == x2:
            continue
        slope = (y2 - y1) / (x2 - x1)
        if abs(slope) < MIN_ABS_SLOPE:
            continue
        mid_x = (x1 + x2) / 2
        # 影像座標 y 向下：左線斜率 < 0、右線斜率 > 0
        if slope < 0 and mid_x < w * 0.6:
            left_pts += [(x1, y1), (x2, y2)]
        elif slope > 0 and mid_x > w * 0.4:
            right_pts += [(x1, y1), (x2, y2)]

    def fit(pts):
        if len(pts) < 2:
            return None
        pts = np.array(pts)
        a, b = np.polyfit(pts[:, 1], pts[:, 0], 1)
        return a, b

    return fit(left_pts), fit(right_pts)


def x_at(line, y):
    a, b = line
    return a * y + b


class LaneDetector:
    def __init__(self, mode="gray"):
        self.mode = mode
        # delta_x(y) = a*y + b，用 (底部值, 頂端值) 兩點定義
        self.delta_bottom = DELTA_X_BOTTOM
        self.delta_top = DELTA_X_TOP

    def delta_x(self, y, h):
        y_top, y_bottom = h * ROI_TOP_Y, h - 1
        t = (y - y_top) / (y_bottom - y_top)
        return self.delta_top + t * (self.delta_bottom - self.delta_top)

    def process(self, frame):
        h, w = frame.shape[:2]
        xc = w / 2
        y_bottom, y_top = h - 1, int(h * ROI_TOP_Y)

        edges, stage = preprocess(frame, self.mode)
        edges = keep_long_edges(edges)
        roi_edges, poly = roi_mask(edges)
        segments = cv2.HoughLinesP(roi_edges, 1, np.pi / 180, HOUGH_THRESHOLD,
                                   minLineLength=HOUGH_MIN_LEN, maxLineGap=HOUGH_MAX_GAP)
        left, right = fit_lanes(segments, w)

        # ---- 中心線 x0(y) ----
        if left and right:
            state = "DOUBLE"
            center = lambda y: (x_at(left, y) + x_at(right, y)) / 2
            # 雙線時量測 delta_x = x2 - x0（講義 p.17），存起來給單線用
            k = DELTA_SMOOTH
            self.delta_bottom = (1 - k) * self.delta_bottom + k * (x_at(right, y_bottom) - center(y_bottom))
            self.delta_top = (1 - k) * self.delta_top + k * (x_at(right, y_top) - center(y_top))
        elif right:
            state = "RIGHT ONLY"
            center = lambda y: x_at(right, y) - self.delta_x(y, h)      # x0 = x2 - delta_x
        elif left:
            state = "LEFT ONLY"
            center = lambda y: x_at(left, y) + self.delta_x(y, h)
        else:
            state = "NO LANE"
            center = None

        out = frame.copy()
        cv2.polylines(out, poly, True, (255, 200, 0), 1)                 # ROI
        for line in (left, right):
            if line:
                p1 = (int(x_at(line, y_bottom)), y_bottom)
                p2 = (int(x_at(line, y_top)), y_top)
                cv2.line(out, p1, p2, (255, 0, 255), 4)                   # 車道線：洋紅
        cv2.line(out, (int(xc), y_top), (int(xc), y_bottom), (0, 255, 0), 1)  # xc：綠

        cte = None
        if center:
            pts = [(int(center(y)), y) for y in range(y_top, h, 10)]
            cv2.polylines(out, [np.array(pts, np.int32)], False, (0, 0, 255), 3)  # 中心線：紅
            x0 = center(y_bottom)
            cte = xc - x0
            cv2.circle(out, (int(x0), y_bottom - 5), 6, (0, 0, 255), -1)

        return out, {"state": state, "cte": cte, "delta_x": self.delta_bottom,
                     "edges": edges, "roi_edges": roi_edges, "stage": stage,
                     "segments": segments, "frame": frame, "left": left, "right": right}


def debug_panel(info, result):
    """把每個步驟縮小拼成 2x3 一張圖（對應講義流程：影像攝取 → 前處理 → Canny → ROI → Hough → 結果）。"""
    frame = info["frame"]
    hough = np.zeros_like(frame)
    if info["segments"] is not None:
        for x1, y1, x2, y2 in info["segments"].reshape(-1, 4):
            cv2.line(hough, (x1, y1), (x2, y2), (0, 255, 255), 2)
    tiles = [
        ("1 Input", frame),
        ("2 Gray / Mask", info["stage"]),
        ("3 Canny + long only", info["edges"]),
        ("4 ROI edges", info["roi_edges"]),
        ("5 Hough segments", hough),
        ("6 Result", result),
    ]
    out = []
    for name, img in tiles:
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        img = cv2.resize(img, (320, 240))
        cv2.rectangle(img, (0, 0), (320, 26), (0, 0, 0), -1)
        cv2.putText(img, name, (8, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        out.append(img)
    return np.vstack([np.hstack(out[0:3]), np.hstack(out[3:6])])


def draw_hud(img, info, fps):
    cte = info["cte"]
    if cte is None:
        cte_txt, side = "CTE: --", ""
    else:
        side = "RIGHT" if cte > 5 else ("LEFT" if cte < -5 else "CENTER")
        cte_txt = f"CTE: {cte:+.1f}px ({side})"
    lines = [f"FPS: {fps:.1f}", info["state"], cte_txt,
             time.strftime("%Y-%m-%d %H:%M:%S")]
    for i, t in enumerate(lines):
        cv2.putText(img, t, (10, 28 + i * 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
        cv2.putText(img, t, (10, 28 + i * 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)


def run_image(path, det):
    frame = cv2.imread(path)
    if frame is None:
        raise SystemExit(f"讀不到圖片：{path}")
    frame = cv2.resize(frame, (WIDTH, HEIGHT))
    out, info = det.process(frame)
    draw_hud(out, info, 0)
    stem = path.rsplit(".", 1)[0]
    cv2.imwrite(f"{stem}_lane.jpg", out)
    cv2.imwrite(f"{stem}_debug.jpg", debug_panel(info, out))
    cte = "--" if info["cte"] is None else f"{info['cte']:+.1f}px"
    print(f"{path}: {info['state']}  CTE={cte}  → {stem}_lane.jpg, {stem}_debug.jpg")


def frames_from_camera(flip, exposure=0, gain=0.0):
    from picamera2 import Picamera2
    cam = Picamera2()
    cam.configure(cam.create_video_configuration(main={"size": (WIDTH, HEIGHT), "format": "RGB888"}))
    cam.start()
    if exposure > 0:
        # 固定短快門避免動態模糊（跟 edge_snap.py 一樣）
        cam.set_controls({"ExposureTime": exposure, "AnalogueGain": gain or 8.0})
    try:
        while True:
            f = cam.capture_array()            # RGB888 在 picamera2 實際是 BGR 排列，可直接給 OpenCV
            yield cv2.flip(f, -1) if flip else f
    finally:
        cam.stop()


def frames_from_video(path):
    cap = cv2.VideoCapture(path)
    while True:
        ok, f = cap.read()
        if not ok:
            break
        yield cv2.resize(f, (WIDTH, HEIGHT))
    cap.release()


def run_stream(frames, det, seconds, out_path, show, debug=False):
    import os
    if debug:
        os.makedirs("debug", exist_ok=True)
    last_dbg = 0.0
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), 20.0, (WIDTH, HEIGHT))
    start = prev = time.time()
    fps = 0.0
    n = 0
    for frame in frames:
        now = time.time()
        inst = 1.0 / (now - prev) if now > prev else 0
        fps = inst if fps == 0 else 0.9 * fps + 0.1 * inst   # 平滑，避免數字亂跳
        prev = now

        out, info = det.process(frame)
        draw_hud(out, info, fps)
        writer.write(out)
        n += 1
        if debug and now - last_dbg >= 2.0:
            last_dbg = now
            cv2.imwrite(f"debug/panel_{int(now - start):03d}s.jpg", debug_panel(info, out))
        if n % 20 == 0:
            cte = "--" if info["cte"] is None else f"{info['cte']:+.1f}"
            print(f"[{now - start:5.1f}s] FPS={fps:4.1f}  {info['state']:<10}  CTE={cte}")
        if show:
            cv2.imshow("lane", out)
            cv2.imshow("edges", info["edges"])
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        if seconds and now - start >= seconds:
            break
    writer.release()
    if show:
        cv2.destroyAllWindows()
    print(f"Done: {out_path}（{n} frames）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["tophat", "gray", "white", "hsv"], default="tophat")
    ap.add_argument("--image", nargs="+", help="可一次給多張，例如 --image track_*.jpg")
    ap.add_argument("--video")
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--out", default="lane_output.mp4")
    ap.add_argument("--no-flip", action="store_true", help="相機沒裝反就加這個")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--debug", action="store_true", help="錄影時每 2 秒存步驟拼圖到 debug/")
    ap.add_argument("--roi-top", type=float, help="ROI 上緣在畫面高度的比例（預設 0.6，越小看越遠）")
    ap.add_argument("--min-edge", type=int, help="長邊過濾的最短長度（預設 120，0 = 關掉）")
    ap.add_argument("--exposure", type=int, default=8000, help="快門微秒，0 = 自動曝光")
    ap.add_argument("--gain", type=float, default=10.0, help="類比增益")
    args = ap.parse_args()

    global ROI_TOP_Y, MIN_EDGE_LEN
    if args.roi_top is not None:
        ROI_TOP_Y = args.roi_top
    if args.min_edge is not None:
        MIN_EDGE_LEN = args.min_edge
    det = LaneDetector(args.mode)
    if args.image:
        for path in args.image:
            run_image(path, det)
    elif args.video:
        run_stream(frames_from_video(args.video), det, 0, args.out, args.show, args.debug)
    else:
        run_stream(frames_from_camera(not args.no_flip, args.exposure, args.gain), det, args.seconds, args.out,
                   args.show, args.debug)


if __name__ == "__main__":
    main()
