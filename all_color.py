import cv2

img_bgr = cv2.imread('input.jpg')

img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

cv2.imshow('Original RGB Image', img_bgr)

cv2.waitKey(0)

cv2.destroyAllWindows()