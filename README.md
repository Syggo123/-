# 嵌入式 AI 與自駕車系統設計 — 第一階段小組作業

> 大同大學 · 2026 秋季學期 · 授課教師：黃家平

## 組員

| 學號 | 姓名 |
|------|------|
| 411002249 | 張庭茂 |
| 411206234 | 洪奕群 |

---

## 實作一：影像色彩轉換

使用 OpenCV + Visual Studio Code，將輸入影像轉換為五種色彩模式。

### 轉換類型

| 類型 | 方法 |
|------|------|
| RGB 全彩 | 原始影像 |
| 灰階 | `cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)` |
| 黑白（二值化） | `cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)` |
| 16 色 | K-Means 聚類（k=16），對彩色影像量化 |
| 256 色 | K-Means 聚類（k=256），對彩色影像量化 |

### 執行方式

```bash
pip install opencv-python numpy
python all_color.py
```

> 需要在同目錄下放置 `input.jpg` 作為輸入影像。

### 檔案說明

| 檔案 | 說明 |
|------|------|
| `all_color.py` | 主程式 |
| `input.jpg` | 原始輸入影像 |
| `gray.jpg` | 灰階輸出 |
| `binary.jpg` | 黑白二值化輸出 |
| `color16.jpg` | 16 色量化輸出 |
| `color256.jpg` | 256 色量化輸出 |

---

## 實作二：人臉識別與辨識

使用 OpenCV + HAAR Cascade 偵測人臉，搭配 LBPH 演算法進行人臉辨識。

### 專案結構

```
LBPH_Face/
├── collect_faces.py    # 收集人臉資料（Webcam）
├── train_lbph.py       # 訓練 LBPH 模型
├── recognize_lbph.py   # 即時人臉辨識
├── data/
│   ├── student01/      # 學生1 人臉照片
│   └── student02/      # 學生2 人臉照片
└── models/
    ├── lbph_model.yml  # 訓練好的模型
    └── labels.json     # 標籤對照表
```

### 執行步驟

```bash
# 1. 收集人臉（每人約 30 張）
python collect_faces.py

# 2. 訓練模型
python train_lbph.py

# 3. 即時辨識
python recognize_lbph.py
```

---

## 實作三：Raspberry Pi 5 環境建置與 PiCamera

### 建置流程

1. Raspberry Pi Imager 燒錄 OS 至 SD 卡
2. SSH 遠端連線（`ssh pi@<IP>`）
3. `sudo apt update && sudo apt upgrade -y`
4. `pip3 install opencv-contrib-python gpiozero picamera2 --break-system-packages --no-cache-dir`
5. PiCamera 拍照測試（`rpicam-still -o test.jpg`）
6. 錄影腳本：FPS + 時間戳即時疊加
7. WinSCP 傳回 Windows → 上傳 YouTube

### 錄影成果

[![YouTube](https://img.shields.io/badge/YouTube-錄影成果-red?logo=youtube)](https://youtu.be/gMUo6e95H-c)

---

## 相關連結

- [HTML 報告（Neocities）](https://TODO.neocities.org)
- [AI 對話紀錄（Claude）](https://claude.ai/share/TODO)
- [YouTube 錄影](https://youtu.be/gMUo6e95H-c)

---

## 工具與技術

![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)
![OpenCV](https://img.shields.io/badge/OpenCV-4.x-green?logo=opencv)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-5-red?logo=raspberrypi)
![PiCamera](https://img.shields.io/badge/PiCamera2-Camera-orange)
# -
