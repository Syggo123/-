import cv2
import os
import json
import numpy as np

data_dir = "data"
os.makedirs("models", exist_ok=True)

faces = []
labels = []
label_map = {}
current_label = 0

for person_name in sorted(os.listdir(data_dir)):
    person_dir = os.path.join(data_dir, person_name)
    if not os.path.isdir(person_dir):
        continue

    label_map[current_label] = person_name

    for img_name in os.listdir(person_dir):
        img_path = os.path.join(person_dir, img_name)
        img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            faces.append(img)
            labels.append(current_label)

    current_label += 1

recognizer = cv2.face.LBPHFaceRecognizer_create()
recognizer.train(faces, np.array(labels))
recognizer.save("models/lbph_model.yml")

with open("models/labels.json", "w", encoding="utf-8") as f:
    json.dump(label_map, f, ensure_ascii=False, indent=2)

print(f"訓練完成，共 {len(faces)} 張臉，{len(label_map)} 人")
print("標籤對照:", label_map)