import numpy as np
import cv2
import os
import util.geometry as ge
import glob
import shelve
from loader import *

_calibrator_path_left = "./data/paramleft"
_calibrator_path_right = "./data/paramright"

# 内参
_camera_matrix_left = load_camera_matrix(_calibrator_path_left)
_camera_distortion_left = load_camera_distortion(_calibrator_path_left)
_camera_tuned_matrix_left = load_camera_matrix_tuned(_calibrator_path_left)

_camera_matrix_right = load_camera_matrix(_calibrator_path_right)
_camera_distortion_right = load_camera_distortion(_calibrator_path_right)
_camera_tuned_matrix_right = load_camera_matrix_tuned(_calibrator_path_right)

print(_camera_tuned_matrix_left,"\n",_camera_tuned_matrix_right)
print(_camera_matrix_left,"\n",_camera_matrix_right)

_remap_x_l, _remap_y_l = cv2.initUndistortRectifyMap(_camera_matrix_left, _camera_distortion_left, None, _camera_tuned_matrix_left,
                                              (CAMERA_WIDTH, CAMERA_HEIGHT), cv2.CV_32FC1)
#

def un_distort_image(image,_remap_x,_remap_y):
    """
    un_distort an image by #remap# api, faster than #undistort# api
    :param image: image to process
    :return: undistorted image
    """
    image = cv2.UMat(image)
    res = cv2.remap(image, _remap_x, _remap_y, cv2.INTER_LINEAR)   # 进行remap
    res = res.get()
    return res

def un_distort_point(point,_camera_matrix, _camera_tuned_matrix, _camera_distortion):
    """
    un_distort a specific point
    :param point: point to distort
    :return: undistorted point
    """

    points = np.array([[(point.x, point.y)]], np.float32)
    temp = cv2.undistortPoints(points, _camera_matrix, _camera_distortion)
    fx, fy = _camera_tuned_matrix[0][0], _camera_tuned_matrix[1][1]
    cx, cy = _camera_tuned_matrix[0][2], _camera_tuned_matrix[1][2]
    x = temp[0][0][0] * fx + cx
    y = temp[0][0][1] * fy + cy
    return ge.Point(x, y)

def pixel2cam(point,_camera_matrix):
    fx, fy = _camera_matrix[0][0], _camera_matrix[1][1]
    cx, cy = _camera_matrix[0][2], _camera_matrix[1][2]
    x = (point.x - cx) / fx
    y = (point.y - cy) / fy
    return ge.Point(x,y)

def _check_calibration(path, _remap_x,_remap_y,_camera_matrix_,_camera_distortion_):
    """
    check if the calibration is correct
    """
    print("path", path)
    image_list = glob.glob(os.path.join(path, "*.bmp"))
    for single_img in image_list:
        image = cv2.imread(single_img)
        #new_image = un_distort_image(image, _remap_x, _remap_y) 
        new_image = cv2.undistort(image,_camera_matrix_,_camera_distortion_)
        #cv2.imshow('before', cv2.resize(image, (int(image.shape[1] * 0.7), int(image.shape[0] * 0.7))))
        #cv2.imshow('after', cv2.resize(new_image, (int(new_image.shape[1] * 0.7), int(new_image.shape[0] * 0.7))))
        cv2.imwrite(path[-3:] + "after-undistort-img.bmp", new_image)
        #cv2.waitKey(0)

def getProjMtx(rvec,tvec):
    rmtx, _ = cv2.Rodrigues(rvec)
    return np.hstack((rmtx,tvec))

def _calibrate_camera(path,tuned_matrix,distor):
    """
    generate calibration matrix ad distortion
    :return: calibration matrix and distortion
    """
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    vertical, horizon = 7, 9  # target corners in vertical and horizontal direction

    grid = np.zeros((vertical * horizon, 3), np.float32)
    grid[:, :2] = np.mgrid[:horizon, :vertical].T.reshape(-1, 2)

    obj_points = []  # 3d point in real world space
    img_points = []  # 2d points in image plane

    image_list = glob.glob(os.path.join(path, "*.bmp"))
    #print(image_list)
    gray = None
    for img_name in image_list:
        print(img_name)
        image = cv2.imread(img_name)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # find the chess board corners
        found, corners = cv2.findChessboardCorners(gray, (horizon, vertical), None)
        #print("corner shape",corners.shape,corners)

        # add object points, image points (after refining them)
        if found:
            obj_points.append(grid)
            corners = cv2.cornerSubPix(gray, corners, (5, 5), (-1, -1), criteria)  #corner是像素坐标 refine 坐标
            img_points.append(corners)
            #print("corner shape",corners.shape,corners)
        else:
            print('can not find %s corners' % img_name)

    #print(corners)
    #print(grid)
    #print("before tuned_matrix\n",_camera_tuned_matrix_right,"\n",_camera_tuned_matrix_left)
    ret, rotation, translation = cv2.solvePnP(obj_points[0], img_points[0], tuned_matrix, distor)

    #ret, matrix, distortion, rotation, translation = \
        #cv2.calibrateCamera(obj_points, img_points, gray.shape[::-1], tuned_matrix, distor,)
        
        #cv2.calibrateCamera([obj_points[-1]], [img_points[-1]], gray.shape[::-1], None, None)
    #print("RT Matrix",np.array(rotation).shape,np.array(translation).shape,rotation)
    #print("after tuned_matrix",_camera_tuned_matrix_right,"\n",_camera_tuned_matrix_left)
    #print("rtMtx:\n",getProjMtx(np.array(rotation[0]),np.array(translation[0])))
    #rtMtx = getProjMtx(np.array(rotation[0]),np.array(translation[0]))
    rtMtx = getProjMtx(rotation,translation)

    mean_err = 0
    err = 0
    for i in range(7):
        for j in range(9):
            _3d = np.array([j,i,0,1])
            _2d = np.dot(np.dot(tuned_matrix,rtMtx),_3d)
            _2d = _2d/_2d[2]
            err = np.sqrt(np.sum(np.square(img_points[0][i * 9 + j ] - _2d[:2])))
            mean_err += err
            print("2d-src:",_2d,img_points[0][i * 9 + j ],err)
    print("err by own: ",mean_err/63)

    #compute all all the err by cv
    mean_error = 0
    for i in range(len(obj_points)):
        new_img_points, _ = cv2.projectPoints(obj_points[i], rotation, translation, tuned_matrix, distor)#3D点投影到平面
        error = cv2.norm(img_points[i], new_img_points, cv2.NORM_L2) / len(new_img_points)
        mean_error += error
        print("cv-proj and old:",new_img_points[1],img_points[i][1])
    print("mean error by cv: ", mean_error / len(obj_points))

    #return np.array(matrix), np.array(distortion)
    return tuned_matrix,rtMtx

matrixl, rtMtxl = _calibrate_camera("C:\\Users\\chuyangl\\Desktop\\liushuai\\calibrator\\board\\left_S",
                                    _camera_matrix_left,_camera_distortion_left)
matrixr, rtMtxr = _calibrate_camera("C:\\Users\\chuyangl\\Desktop\\liushuai\\calibrator\\board\\right_S",
                                    _camera_matrix_right,_camera_distortion_right)  
#print("matrix_tuned\n",_camera_tuned_matrix_right)
#print("matrixr\n",matrixr)
projl = np.dot(matrixl,rtMtxl)
projr = np.dot(matrixr,rtMtxr)
#print(projl,projr)
_3dl = np.array([4.2,0.8,0,1])
_2dl = np.dot(projl,_3dl)
_2dl = _2dl/_2dl[2]
_2dl = np.array([_2dl]).T

_3dr = np.array([2.7,0.7,0,1])
_2dr = np.dot(projr,_3dr)
_2dr = _2dr/_2dr[2]
_2dr = np.array([_2dr]).T
print("_2dl,_2dr",_2dl,"\n", _2dr)

# The cv2 method
#X = cv2.triangulatePoints( projl, projr, a3xN[:2], b3xN[:2] )  # coor 
_2dl = np.array([[501.0, 404., 426.],
                [188.0, 181. ,180.],
                [1., 1. ,1.]])
_2dr = np.array([[130.0, 66., 91],
                [180.0, 168.,166.],
                [1., 1., 1.]])


X = cv2.triangulatePoints( projl, projr, _2dl[:2], _2dr[:2] )  # coor 
# Remember to divide out the 4th row. Make it homogeneous
X /= X[3]
# Recover the origin arrays from PX
x1 = np.dot(projl,X)
x2 = np.dot(projr,X)
# Again, put in homogeneous form before using them
x1 /= x1[2]
x2 /= x2[2]
 
print('X\n',X)
print('x1\n',x1)
print('x2\n',x2)


pl = ge.Point(498.0, 186.)
pr = ge.Point(130., 179.)
pl = pixel2cam(pl, matrixl)
pr = pixel2cam(pr, matrixr)

_2dl = np.array([[pl.x, 404., 447.],
                [pl.y, 181. ,180.],
                [1., 1. ,1.]])
_2dr = np.array([[pr.x, 70., 96],
                [pr.y, 168.,170.],
                [1., 1., 1.]])

X = cv2.triangulatePoints( projl, projr, _2dl[:2], _2dr[:2] )  # coor 
# Remember to divide out the 4th row. Make it homogeneous
X /= X[3]
# Recover the origin arrays from PX
x1 = np.dot(projl,X)
x2 = np.dot(projr,X)
# Again, put in homogeneous form before using them
x1 /= x1[2]
x2 /= x2[2]
 
print('X\n',X)
print('x1\n',x1)
print('x2\n',x2)
pathl = "C:\\Users\\chuyangl\\Desktop\\liushuai\\calibrator\\board\\stereo\\left"
pathr = "C:\\Users\\chuyangl\\Desktop\\liushuai\\calibrator\\board\\stereo\\right"
_check_calibration(pathl, _remap_x_l, _remap_y_l, _camera_matrix_left, _camera_distortion_left)
_check_calibration(pathr, _remap_x_l, _remap_y_l, _camera_matrix_right, _camera_distortion_right)