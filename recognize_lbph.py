import cv2
import json

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt.xml")
recognizer = cv2.face.LBPHFaceRecognizer_create()
recognizer.read("models/lbph_model.yml")

with open("models/labels.json", "r", encoding="utf-8") as f:
    label_map = json.load(f)

THRESHOLD = 80
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 3)

    for (x, y, w, h) in faces:
        face_img = gray[y:y + h, x:x + w]
        label, distance = recognizer.predict(face_img)

        if distance <= THRESHOLD:
            name = label_map.get(str(label), "Unknown")
            color = (0, 255, 0)
        else:
            name = "Unknown"
            color = (0, 0, 255)

        text = f"{name} ({distance:.1f})"
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.putText(frame, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    cv2.imshow("Face Recognition", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()