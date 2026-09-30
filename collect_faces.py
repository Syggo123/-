import cv2
import os

name = input("輸入姓名（如 student01）: ")
save_dir = os.path.join("data", name)
os.makedirs(save_dir, exist_ok=True)

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt.xml")
cap = cv2.VideoCapture(0)
count = 0

print("按 s 拍照，按 q 結束")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 3)

    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    cv2.imshow("Collect Faces", frame)
    key = cv2.waitKey(1) & 0xFF

    if key == ord("s") and len(faces) > 0:
        x, y, w, h = faces[0]
        face_img = gray[y:y + h, x:x + w]
        count += 1
        filepath = os.path.join(save_dir, f"{count}.jpg")
        cv2.imwrite(filepath, face_img)
        print(f"已儲存 {filepath}（共 {count} 張）")

    elif key == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
print(f"完成，共拍了 {count} 張")