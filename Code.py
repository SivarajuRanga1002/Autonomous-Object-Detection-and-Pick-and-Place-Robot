#!/usr/bin/env python3
import cv2
import numpy as np
import time
import os
import sys
import serial
import serial.tools.list_ports
from pymycobot.mycobot import MyCobot

IS_CV_4 = cv2.__version__[0] == '4'
__version__ = "1.0"

# Adaptive seeed
class Object_detect:
    def __init__(self, camera_x=160, camera_y=15):
        # inherit the parent class
        super(Object_detect, self).__init__()
        # declare mycobot280
        self.mc = None
        # get real serial
        self.plist = [str(x).split(" - ")[0].strip() for x in serial.tools.list_ports.comports()]

        # 移动角度 (Moving angles)
        self.move_angles = [
            [0.61, 45.87, -92.37, -41.3, 2.02, 9.58],  # init the point
            [18.8, -7.91, -54.49, -23.02, -0.79, -14.76],  # point to grab
        ]
        # 移动坐标 (Moving coordinates)
        self.move_coords = [
            [132.2, -136.9, 200.8, -178.24, -3.72, -107.17],  # D Sorting area
            [238.8, -124.1, 204.3, -169.69, -5.52, -96.52],  # C Sorting area
            [115.8, 177.3, 210.6, 178.06, -0.92, -6.11],  # A Sorting area
            [-6.9, 173.2, 201.5, 179.93, 0.63, 33.83],  # B Sorting area
        ]

        # choose place to set cube 选择放置立方体的地方
        self.color = 0
        # parameters to calculate camera clipping parameters 计算相机裁剪参数的参数
        self.x1 = self.x2 = self.y1 = self.y2 = 0
        # set cache of real coord 设置真实坐标的缓存
        self.cache_x = self.cache_y = 0
        # set color HSV
        self.HSV = {
            "yellow": [np.array([11, 85, 70]), np.array([59, 255, 245])],
            "red": [np.array([0, 43, 46]), np.array([8, 255, 255])],
            "green": [np.array([35, 43, 35]), np.array([90, 255, 255])],
            "blue": [np.array([100, 43, 46]), np.array([124, 255, 255])],
            "cyan": [np.array([78, 43, 46]), np.array([99, 255, 255])],
        }

        # use to calculate coord between cube and mycobot280
        self.sum_x1 = self.sum_x2 = self.sum_y2 = self.sum_y1 = 0
        # The coordinates of the grab center point relative to the mycobot280
        self.camera_x, self.camera_y = camera_x, camera_y
        # The coordinates of the cube relative to the mycobot280
        self.c_x, self.c_y = 0, 0
        # The ratio of pixels to actual values
        self.ratio = 0

        # Get ArUco marker dict that can be detected.
        self.aruco_dict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_6X6_250)
        # Get ArUco marker params.
        self.aruco_params = cv2.aruco.DetectorParameters_create()

    # 开启吸泵 (Turn on the pump)
    def pump_on(self):
        self.mc.set_basic_output(2, 0)
        self.mc.set_basic_output(5, 0)

    # 停止吸泵 (Turn off the pump)
    def pump_off(self):
        self.mc.set_basic_output(2, 1)
        self.mc.set_basic_output(5, 1)

    # Grasping motion
    def move(self, x, y, color):
        print(color)
        self.mc.send_angles(self.move_angles[1], 25)
        time.sleep(3)
        self.mc.send_coords([x, y, 170.6, 179.87, -3.78, -62.75], 25, 1)
        time.sleep(3)
        self.mc.send_coords([x, y, 103, 179.87, -3.78, -62.75], 25, 0)
        time.sleep(3)
        # open pump
        self.pump_on()
        time.sleep(1.5)
        tmp = []
        while True:
            if not tmp:
                tmp = self.mc.get_angles()
            else:
                break
            time.sleep(0.5)
        self.mc.send_angles([tmp[0], -0.71, -54.49, -23.02, -0.79, tmp[5]], 25)
        time.sleep(3)
        self.mc.send_coords(self.move_coords[color], 25, 1)
        time.sleep(3)
        # close pump
        self.pump_off()
        time.sleep(5)
        self.mc.send_angles(self.move_angles[0], 25)
        time.sleep(4.5)

    # decide whether to grab the cube 决定是否抓取立方体
    def decide_move(self, x, y, color):
        print(x, y, self.cache_x, self.cache_y)
        # detect the cube status move or run 检测立方体状态移动或运行
        if (abs(x - self.cache_x) + abs(y - self.cache_y)) / 2 > 5:  # mm
            self.cache_x, self.cache_y = x, y
            return
        else:
            self.cache_x = self.cache_y = 0
            self.move(x, y, color)

    # init mycobot280
    def run(self):
        self.mc = MyCobot(self.plist[0], 115200)
        self.mc.send_angles([0.61, 45.87, -92.37, -41.3, 2.02, 9.58], 20)
        time.sleep(2.5)

    # draw aruco marker
    def draw_marker(self, img, x, y):
        # draw rectangle on img 在 img 上绘制矩形
        cv2.rectangle(
            img,
            (x - 20, y - 20),
            (x + 20, y + 20),
            (0, 255, 0),
            thickness=2,
            lineType=cv2.FONT_HERSHEY_COMPLEX,
        )
        # add text on rectangle
        cv2.putText(img, "({},{})".format(x, y), (x, y), cv2.FONT_HERSHEY_COMPLEX_SMALL, 1, (243, 0, 0), 2)

    # get points of two aruco markers 获得两个 aruco 的点位
    def get_calculate_params(self, img):
        # Convert the image to a gray image 将图像转换为灰度图像
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Detect ArUco marker.
        corners, ids, _ = cv2.aruco.detectMarkers(gray, self.aruco_dict, parameters=self.aruco_params)

        if len(corners) > 0 and ids is not None and len(corners) > 1 and ids[0] == 1:
            x1 = x2 = y1 = y2 = 0
            point_11, point_21, point_31, point_41 = corners[0][0]
            x1, y1 = int((point_11[0] + point_21[0] + point_31[0] + point_41[0]) / 4.0), int(
                (point_11[1] + point_21[1] + point_31[1] + point_41[1]) / 4.0)
            point_1, point_2, point_3, point_4 = corners[1][0]
            x2, y2 = int((point_1[0] + point_2[0] + point_3[0] + point_4[0]) / 4.0), int(
                (point_1[1] + point_2[1] + point_3[1] + point_4[1]) / 4.0)
            return x1, x2, y1, y2
        return None

    # set camera clipping parameters 设置相机裁剪参数
    def set_cut_params(self, x1, y1, x2, y2):
        self.x1 = int(x1)
        self.y1 = int(y1)
        self.x2 = int(x2)
        self.y2 = int(y2)

    # set parameters to calculate the coords between cube and mycobot280 设置参数以计算立方体和 mycobot 之间的坐标
    def set_params(self, c_x, c_y, ratio):
        self.c_x = c_x
        self.c_y = c_y
        self.ratio = 220.0 / ratio

    # calculate the coords between cube and mycobot280 计算立方体和 mycobot 之间的坐标
    def get_position(self, x, y):
        return ((y - self.c_y) * self.ratio + self.camera_x), ((x - self.c_x) * self.ratio + self.camera_y)

    # transform the frame
    def transform_frame(self, frame):
        # enlarge the image by 1.5 times
        fx = 1.5
        fy = 1.5
        frame = cv2.resize(frame, (0, 0), fx=fx, fy=fy, interpolation=cv2.INTER_CUBIC)
        if self.x1 != self.x2:
            # the cutting ratio here is adjusted according to the actual situation
            frame = frame[int(self.y2 * 0.78):int(self.y1 * 1.1), int(self.x1 * 0.86):int(self.x2 * 1.08)]
        return frame

    # detect cube color
    def color_detect(self, img):
        x = y = 0
        for mycolor, item in self.HSV.items():
            redLower = np.array(item[0])
            redUpper = np.array(item[1])
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, item[0], item[1])
            erosion = cv2.erode(mask, np.ones((1, 1), np.uint8), iterations=2)
            dilation = cv2.dilate(erosion, np.ones((1, 1), np.uint8), iterations=2)
            target = cv2.bitwise_and(img, img, mask=dilation)
            ret, binary = cv2.threshold(dilation, 127, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(dilation, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if len(contours) > 0:
                boxes = [box for box in [cv2.boundingRect(c) for c in contours] if min(img.shape[0], img.shape[1]) / 10 < min(box[2], box[3]) < min(img.shape[0], img.shape[1]) / 1]
                if boxes:
                    for box in boxes:
                        x, y, w, h = box
                        c = max(contours, key=cv2.contourArea)
                        x, y, w, h = cv2.boundingRect(c)
                        cv2.rectangle(img, (x, y), (x + w, y + h), (153, 153, 0), 2)
                        x, y = (x * 2 + w) / 2, (y * 2 + h) / 2
                        if mycolor == "yellow":
                            self.color = 3
                            break
                        elif mycolor == "red":
                            self.color = 0
                            break
                        elif mycolor == "cyan":
                            self.color = 2
                            break
                        elif mycolor == "blue":
                            self.color = 2
                            break
                        elif mycolor == "green":
                            self.color = 1
                            break
        if abs(x) + abs(y) > 0:
            return x, y
        return None


if __name__ == "__main__":
    import platform

    # open the camera
    if platform.system() == "Windows":
        cap_num = 1
        cap = cv2.VideoCapture(cap_num, cv2.CAP_V4L)
        if not cap.isOpened():
            cap.open(1)
    elif platform.system() == "Linux":
        cap_num = 0
        cap = cv2.VideoCapture(cap_num, cv2.CAP_V4L)
        if not cap.isOpened():
            cap.open()

    # init a class of Object_detect
    detect = Object_detect()
    # init mycobot280
    detect.run()
    _init_ = 20
    init_num = 0
    nparams = 0
    num = 0
    real_sx = real_sy = 0

    while cv2.waitKey(1) < 0:
        # read camera
        _, frame = cap.read()
        # deal img
        frame = detect.transform_frame(frame)
        if _init_ > 0:
            _init_ -= 1
            continue

        # calculate the parameters of camera clipping 计算相机裁剪的参数
        if init_num < 20:
            if detect.get_calculate_params(frame) is None:
                cv2.imshow("figure", frame)
                continue
            else:
                x1, x2, y1, y2 = detect.get_calculate_params(frame)
                detect.draw_marker(frame, x1, y1)
                detect.draw_marker(frame, x2, y2)
                detect.sum_x1 += x1
                detect.sum_x2 += x2
                detect.sum_y1 += y1
                detect.sum_y2 += y2
                init_num += 1
                continue
        elif init_num == 20:
            detect.set_cut_params(
                (detect.sum_x1) / 20.0,
                (detect.sum_y1) / 20.0,
                (detect.sum_x2) / 20.0,
                (detect.sum_y2) / 20.0,
            )
            detect.sum_x1 = detect.sum_x2 = detect.sum_y1 = detect.sum_y2 = 0
            init_num += 1
            continue

        # calculate params of the coords between cube and mycobot280 计算立方体和 mycobot 之间坐标的参数
        if nparams < 10:
            if detect.get_calculate_params(frame) is None:
                cv2.imshow("figure", frame)
                continue
            else:
                x1, x2, y1, y2 = detect.get_calculate_params(frame)
                detect.draw_marker(frame, x1, y1)
                detect.draw_marker(frame, x2, y2)
                detect.sum_x1 += x1
                detect.sum_x2 += x2
                detect.sum_y1 += y1
                detect.sum_y2 += y2
                nparams += 1
                continue
        elif nparams == 10:
            nparams += 1
            # calculate and set params of calculating real coord between cube and mycobot280
            detect.set_params(
                (detect.sum_x1 + detect.sum_x2) / 20.0,
                (detect.sum_y1 + detect.sum_y2) / 20.0,
                abs(detect.sum_x1 - detect.sum_x2) / 10.0 + abs(detect.sum_y1 - detect.sum_y2) / 10.0
            )
            print("ok")
            continue

        # get detect result 获取检测结果
        detect_result = detect.color_detect(frame)
        if detect_result is None:
            cv2.imshow("figure", frame)
            continue
        else:
            x, y = detect_result
            # calculate real coord between cube and mycobot280 计算立方体和 mycobot 之间的真实坐标
            real_x, real_y = detect.get_position(x, y)
            if num == 20:
                detect.decide_move(real_sx / 20.0, real_sy / 20.0, detect.color)
                num = real_sx = real_sy = 0
            else:
                num += 1
                real_sy += real_y
                real_sx += real_x
            cv2.imshow("figure", frame)

        # close the window
        if cv2.waitKey(1) & 0xFF == ord('q'):
            cap.release()
            cv2.destroyAllWindows()
            sys.exit()
