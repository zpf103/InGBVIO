# msckf_simu
import numpy as np
from scipy.linalg import expm
from scipy.linalg import qr

import matplotlib.pyplot as plt

from tqdm import tqdm
from scipy.spatial.transform import Rotation as Rot

import time

def sph2cart(_azimuth, _elevation, _r):
    _l = np.size(_azimuth)
    _x = []
    _y = []
    _z = []
    for i in range(_l):
        _x.append(_r * np.cos(_azimuth[i]) * np.cos(_elevation))
        _y.append(_r * np.sin(_azimuth[i]) * np.cos(_elevation))
        _z.append(_r * np.sin(_elevation))
    _x = np.array(_x).flatten()
    _y = np.array(_y).flatten()
    _z = np.array(_z).flatten()
    return _x, _y, _z

def euler2rot(euler):
    roll = euler[0]
    _pitch = euler[1]
    _yaw = euler[2]
    cr = np.cos(roll)
    sr = np.sin(roll)
    cp = np.cos(_pitch)
    sp = np.sin(_pitch)
    cy = np.cos(_yaw)
    sy = np.sin(_yaw)
    _N = np.size(roll)
    _Rot = np.zeros((3, 3, _N))
    _Rot[0, 0, :] = cp * cy
    _Rot[0, 1, :] = cy * sp * sr - cr * sy
    _Rot[0, 2, :] = sr * sy + cr * cy * sp
    _Rot[1, 0, :] = cp * sy
    _Rot[1, 1, :] = cr * cy + sr * sp * sy
    _Rot[1, 2, :] = cr * sp * sy - cy * sr
    _Rot[2, 0, :] = -sp
    _Rot[2, 1, :] = cp * sr
    _Rot[2, 2, :] = cp * cr
    return _Rot

def eulerRates2bodyRates(euler, eulerRates):
    roll = euler[0]
    _pitch = euler[1]
    _yaw = euler[2]
    cr = np.cos(roll)
    sr = np.sin(roll)
    cp = np.cos(_pitch)
    sp = np.sin(_pitch)
    cy = np.cos(_yaw)
    sy = np.sin(_yaw)
    _N = np.size(roll)
    _bodyRates = np.zeros((3, _N))
    _bodyRates[0, :] = eulerRates[0] - sp * eulerRates[2]
    _bodyRates[1, :] = cr * eulerRates[1] + sr * cp * eulerRates[2]
    _bodyRates[2, :] = -sr * eulerRates[1] + cr * cp * eulerRates[2]
    return _bodyRates

def worldacc2bodyacc(_Rot, _acc):
    _N = np.size(_acc, 1)
    _bodyacc = np.zeros((3, _N))
    for i in range(_N):
        _bodyacc[:, i] = np.dot(_Rot[:, :, i].T, _acc[:, i] + np.array([[0], [0], [9.8]]).reshape(3))
    return _bodyacc

def skew(_v):
    _skew = np.zeros((3, 3))
    _v = _v.flatten()
    _skew[0, 1] = -_v[2]
    _skew[0, 2] = _v[1]
    _skew[1, 0] = _v[2]
    _skew[1, 2] = -_v[0]
    _skew[2, 0] = -_v[1]
    _skew[2, 1] = _v[0]
    return _skew

def gamma(_v, n):
    _result = np.zeros((3, 3))
    _theta = np.linalg.norm(_v)
    _v_norm = _v / _theta
    _v_cross = skew(_v_norm)
    _v_cross2 = np.dot(_v_cross, _v_cross)
    _cos = np.cos(_theta)
    _sin = np.sin(_theta)
    match n:
        case 1:
            _factor0 = 1.0
            _factor1 = (1.0 - _cos) / _theta
            _factor2 = (_theta - _sin) / _theta
        case 2:
            _factor0 = 0.5
            _factor1 = (_theta - _sin) / (_theta ** 2)
            _factor2 = (_theta ** 2 + 2 * _cos - 2) / (2 * _theta * _theta)
        case default:
            _factor0 = 1.0
            _factor1 = _sin
            _factor2 = 1.0 - _cos
    _result = _factor0 * np.eye(3) + _factor1 * _v_cross + _factor2 * _v_cross2
    return _result

def triangulate_multi_initial_guess(feats, clones):
    _A = np.zeros((3, 3))
    b = np.zeros((3, 1))
    clone_count = len(feats)
    k_anchor = min(feats.keys())
    T_G_A = np.eye(4)
    T_G_A[0:3, 0:3] = clones[k_anchor]['R'].T
    T_G_A[0:3, 3] = clones[k_anchor]['p'].reshape(3)
    for _k in feats.keys():
        feat_k = feats[_k]
        bi = np.array(([feat_k[0], feat_k[1], 1]))

        T_G_Ci = np.eye(4)
        T_G_Ci[0:3, 0:3] = clones[_k]['R'].T
        T_G_Ci[0:3, 3] = clones[_k]['p'].reshape(3)
        T_A_Ci = np.linalg.inv(T_G_A) @ T_G_Ci
        # R_G_Ci = T_G_Ci[0:3, 0:3]
        R_A_Ci = np.reshape(T_A_Ci[0:3, 0:3], (3, 3))
        # p_Ci_in_G = T_G_Ci[0:3, 3]
        p_Ci_in_A = np.reshape(T_A_Ci[0:3, 3], (3, 1))
        bi = R_A_Ci @ bi
        binorm = np.linalg.norm(bi)
        bi = bi / binorm
        B = skew(bi)
        Ai = np.matmul(B.T, B)
        _A += Ai
        b += np.matmul(Ai, p_Ci_in_A)
    pf = np.linalg.solve(_A, b)
    cond = np.linalg.cond(_A)
    pf = np.reshape(pf, (3, 1))
    if pf[2][0] < 0.2:
        _pf_G = T_G_A[0:3] @ np.array([[pf[0][0], pf[1][0], pf[2][0], 1]]).T
        return _pf_G, False
    _pf_G = T_G_A[0:3] @ np.array([[pf[0][0], pf[1][0], pf[2][0], 1]]).T

    return _pf_G, True

def compute_err(x, clones, feats):
    err = 0
    grad = np.zeros((3, 1))
    uv_count = len(feats)
    alpha = x[0]
    beta = x[1]
    rho = x[2]
    uv_A = np.array([alpha[0], beta[0], 1])
    uv_A = np.reshape(uv_A, (3, 1))
    k_anchor = min(feats.keys())
    T_G_A = np.eye(4)
    T_G_A[0:3, 0:3] = clones[k_anchor]['R'].T
    T_G_A[0:3, 3] = clones[k_anchor]['p'].reshape(3)
    for _key in feats.keys():
        T_G_Ci = np.eye(4)
        T_G_Ci[0:3, 0:3] = clones[_key]['R'].T
        T_G_Ci[0:3, 3] = clones[_key]['p'].reshape(3)
        T_A_Ci = np.linalg.inv(T_G_A) @ T_G_Ci
        # R_Ci_G = T[0:3, 0:3]
        # R_Ci_G = np.reshape(T[0:3, 0:3], (3, 3))
        # p_Ci_in_G = T[0:3, 3]
        p_Ci_in_A = np.reshape(T_A_Ci[0:3, 3], (3, 1))
        R_Ci_A = np.reshape(T_A_Ci[0:3, 0:3], (3, 3)).T
        test_e = uv_A - rho[0] * p_Ci_in_A
        h = R_Ci_A @ (uv_A - rho[0] * p_Ci_in_A)
        z = np.array([h[0][0] / h[2][0], h[1][0] / h[2][0]])
        res = z - feats[_key]
        err += res[0] ** 2 + res[1] ** 2
    return err

def triangulate_gauss_newton(x, clones, feats):
    x = np.reshape(x, (3, 1))
    Hess = np.zeros((3, 3))
    grad = np.zeros((3, 1))

    runs = 0
    recompute = True
    uv_count = len(feats)
    lam = 1e-3

    eps = 1000
    k_anchor = min(feats.keys())
    T_G_A = np.eye(4)
    T_G_A[0:3, 0:3] = clones[k_anchor]['R'].T
    T_G_A[0:3, 3] = clones[k_anchor]['p'].reshape(3)

    T_A_G = np.linalg.inv(T_G_A)
    x_A = T_A_G[0:3] @ np.array([[x[0][0], x[1][0], x[2][0], 1]]).T
    inv_dep = np.array([x_A[0][0] / x_A[2][0], x_A[1][0] / x_A[2][0], 1 / x_A[2][0]])
    inv_dep = np.reshape(inv_dep, (3, 1))
    cost_old = compute_err(inv_dep, clones, feats)
    while runs < 15 and eps > 1e-6 and lam < 1e10:
        if recompute:
            Hess = np.zeros((3, 3))
            grad = np.zeros((3, 1))
            err = 0
            for _k in feats.keys():
                T_G_Ci = np.eye(4)
                T_G_Ci[0:3, 0:3] = clones[_k]['R'].T
                T_G_Ci[0:3, 3] = clones[_k]['p'].reshape(3)
                T_A_Ci = np.linalg.inv(T_G_A) @ T_G_Ci
                # R_Ci_G = T[0:3, 0:3]
                R_Ci_A = np.reshape(T_A_Ci[0:3, 0:3], (3, 3)).T
                # p_Ci_in_G = T[0:3, 3]
                p_Ci_in_A = np.reshape(T_A_Ci[0:3, 3], (3, 1))
                # R_G_Ci = R_Ci_G.T
                p_AinCi = -1 * R_Ci_A @ p_Ci_in_A
                alpha = inv_dep[0]
                beta = inv_dep[1]
                rho = inv_dep[2]
                uv_A = np.array(([[alpha[0], beta[0], 1]])).T
                h = R_Ci_A @ (uv_A - rho[0] * p_Ci_in_A)
                d_z1_d_alpha = (R_Ci_A[0, 0] * h[2] - h[0] * R_Ci_A[2, 0]) / (pow(h[2], 2))
                d_z1_d_beta = (R_Ci_A[0, 1] * h[2] - h[0] * R_Ci_A[2, 1]) / (pow(h[2], 2))
                d_z1_d_rho = (p_AinCi[0, 0] * h[2] - h[0] * p_AinCi[2, 0]) / (pow(h[2], 2))
                d_z2_d_alpha = (R_Ci_A[1, 0] * h[2] - h[1] * R_Ci_A[2, 0]) / (pow(h[2], 2))
                d_z2_d_beta = (R_Ci_A[1, 1] * h[2] - h[1] * R_Ci_A[2, 1]) / (pow(h[2], 2))
                d_z2_d_rho = (p_AinCi[1, 0] * h[2] - h[1] * p_AinCi[2, 0]) / (pow(h[2], 2))
                H = np.array([
                    [d_z1_d_alpha[0], d_z1_d_beta[0], d_z1_d_rho[0]],
                    [d_z2_d_alpha[0], d_z2_d_beta[0], d_z2_d_rho[0]],
                ])
                z = np.array(([[h[0] / h[2], h[1] / h[2]]]))
                z = np.reshape(z, (2, 1))
                # res = feats[_k, :] - z
                res = np.reshape(feats[_k], (2, 1)) - z
                grad += H.T @ res
                Hess += H.T @ H
        for _k in np.arange(3):
            Hess[_k, _k] *= (1 + lam)
        dx = np.linalg.solve(Hess, grad)
        test_d = inv_dep + dx
        cost = compute_err(inv_dep + dx, clones, feats)
        if cost < cost_old and (cost_old - cost) / cost_old < 1e-6:
            inv_dep += dx
            eps = 0
            break
        if cost <= cost_old:
            recompute = True
            cost_old = cost
            inv_dep += dx
            lam = lam / 10
            eps = np.linalg.norm(dx)
            runs += 1
        else:
            recompute = False
            lam = lam * 10
            continue
    x = np.array([inv_dep[0] / inv_dep[2], inv_dep[1] / inv_dep[2], 1 / inv_dep[2]])
    x = np.reshape(x, (3, 1))
    # Qf, Rf = qr(_x)
    # Qf = Qf[:, 1:3]
    # max_baseline = 0
    # for _k in np.arange(uv_count):
    #     T_G_Ci = _clones[_k]
    #     T_A_Ci = np.linalg.inv(T_G_A) @ T_G_Ci
    #     p_Ci_in_A = np.reshape(T_A_Ci[0:3, 3], (3, 1))
    #     baseline = Qf.T @ p_Ci_in_A
    #     baseline = np.linalg.norm(baseline)
    #     max_baseline = max(max_baseline, baseline)
    # L = np.linalg.norm(_x)
    if x[2][0] < 0.2:
        x_G = T_G_A[0:3] @ np.array([[x[0][0], x[1][0], x[2][0], 1]]).T
        x = np.array(([-1.0, -1.0, -1.0]))
        return x_G, False
    x_G = T_G_A[0:3] @ np.array([[x[0][0], x[1][0], x[2][0], 1]]).T
    return x_G, True

def exp_lie(_v):
    N = int((len(_v) - 3) / 3)
    Lg = np.zeros((N + 3, N + 3))
    # Lg[0:3, :] = np.block([
    #     [skew(_v[0:3]), np.reshape(_v[3:], (3, -1))],
    # ])
    Lg[0:3, 0:3] = skew(_v[0:3])
    if len(_v) == 6:
        Lg[0:3, 3] = np.reshape(_v[3:6], 3)
    else:
        Lg[0:3, 3] = np.reshape(_v[3:6], 3)
        Lg[0:3, 4] = np.reshape(_v[6:9], 3)
    dx = expm(Lg)
    return dx

def Jl_so3(w):
    theta = np.linalg.norm(w)
    if theta < 1e-6:
        return np.eye(3)
    else:
        a = w / theta
        J = (np.sin(theta) / theta) * np.eye(3) + (1 - np.sin(theta) / theta) * np.outer(a, a) + \
            ((1 - np.cos(theta)) / theta) * skew(a)
        return J

def Jr_so3(w):
    return Jl_so3(-w)

def exp_so3(w):
    w_x = skew(w)
    theta = np.linalg.norm(w)
    if theta < 1e-7:
        A = 1
        B = 0.5
    else:
        A = np.sin(theta) / theta
        B = (1 - np.cos(theta)) / (theta ** 2)
    if theta == 0:
        R = np.eye(3)
    else:
        R = np.eye(3) + A * w_x + B * np.dot(w_x, w_x)
    return R

def compute_Xi_sum(dt, w_hat, a_hat):
    w_norm = np.linalg.norm(w_hat)
    d_th = w_norm * dt
    k_hat = np.zeros(3)
    if w_norm > 1e-12:
        k_hat = w_hat / w_norm

    I_3x3 = np.eye(3)
    d_t2 = dt ** 2
    d_t3 = dt ** 3
    w_norm2 = w_norm ** 2
    w_norm3 = w_norm ** 3
    cos_dth = np.cos(d_th)
    sin_dth = np.sin(d_th)
    d_th2 = d_th ** 2
    d_th3 = d_th ** 3
    sK = skew(k_hat)
    sK2 = np.dot(sK, sK)
    sA = skew(a_hat)

    R_ktok1 = exp_so3(-w_hat * dt)
    Jr_ktok1 = Jr_so3(-w_hat * dt)

    small_w = (w_norm < 1.0 / 180 * np.pi / 2)
    if not small_w:
        Xi_1 = I_3x3 * dt + (1.0 - cos_dth) / w_norm * sK + (dt - sin_dth / w_norm) * sK2
        Xi_2 = 0.5 * d_t2 * I_3x3 + (d_th - sin_dth) / w_norm2 * sK + (0.5 * d_t2 - (1.0 - cos_dth) / w_norm2) * sK2
        Xi_3 = 0.5 * d_t2 * sA + (sin_dth - d_th) / w_norm2 * np.dot(sA, sK) + (sin_dth - d_th * cos_dth) / w_norm2 * np.dot(sK, sA) + \
               (0.5 * d_t2 - (1.0 - cos_dth) / w_norm2) * np.dot(sA, sK2) + \
               (0.5 * d_t2 + (1.0 - cos_dth - d_th * sin_dth) / w_norm2) * (np.dot(sK2, sA) + np.dot(k_hat.T, a_hat) * sK) - \
               (3 * sin_dth - 2 * d_th - d_th * cos_dth) / w_norm2 * np.dot(k_hat.T, a_hat) * sK2
        Xi_4 = 1.0 / 6 * d_t3 * sA + (2 * (1.0 - cos_dth) - d_th2) / (2 * w_norm3) * np.dot(sA, sK) + \
               ((2 * (1.0 - cos_dth) - d_th * sin_dth) / w_norm3) * np.dot(sK, sA) + ((sin_dth - d_th) / w_norm3 + d_t3 / 6) * np.dot(sA, sK2) + \
               ((d_th - 2 * sin_dth + 1.0 / 6 * d_th3 + d_th * cos_dth) / w_norm3) * (np.dot(sK2, sA) + np.dot(k_hat.T, a_hat) * sK) + \
               (4 * cos_dth - 4 + d_th2 + d_th * sin_dth) / w_norm3 * np.dot(k_hat.T, a_hat) * sK2
    else:
        Xi_1 = dt * (I_3x3 + sin_dth * sK + (1.0 - cos_dth) * sK2)
        Xi_2 = 0.5 * dt * Xi_1
        Xi_3 = 0.5 * d_t2 * (sA + sin_dth * (-np.dot(sA, sK) + np.dot(sK, sA) + np.dot(k_hat.T, a_hat) * sK2) + (1.0 - cos_dth) * (np.dot(sA, sK2) + np.dot(sK2, sA) + np.dot(k_hat.T, a_hat) * sK))
        Xi_4 = 1.0 / 3 * dt * Xi_3

    Xi_sum = np.zeros((3, 18))
    Xi_sum[:, 0:3] = R_ktok1
    Xi_sum[:, 3:6] = Xi_1
    Xi_sum[:, 6:9] = Xi_2
    Xi_sum[:, 9:12] = Jr_ktok1
    Xi_sum[:, 12:15] = Xi_3
    Xi_sum[:, 15:18] = Xi_4
    return Xi_sum

def quat_multiply(q, p):
    Qm = np.zeros((4, 4))
    # create big L matrix
    Qm[0:3, 0:3] = q[3] * np.eye(3) - skew(q[0:3])
    Qm[0:3, 3] = q[0:3]
    Qm[3, 0:3] = -q[0:3].T
    Qm[3, 3] = q[3]
    q_t = np.dot(Qm, p)
    # ensure unique by forcing q_4 to be >0
    if q_t[3] < 0:
        q_t *= -1
    # normalize and return
    return q_t / np.linalg.norm(q_t)

def quat_2_Rot(q):
    q_x = skew(q[:3])
    Rot = (2 * q[3]**2 - 1) * np.eye(3) - 2 * q[3] * q_x + 2 * np.outer(q[:3], q[:3])
    return Rot

def rot_2_quat(rot):
    q = np.zeros(4)
    T = np.trace(rot)
    if (rot[0, 0] >= T) and (rot[0, 0] >= rot[1, 1]) and (rot[0, 0] >= rot[2, 2]):
        q[0] = np.sqrt((1 + (2 * rot[0, 0]) - T) / 4)
        q[1] = (1 / (4 * q[0])) * (rot[0, 1] + rot[1, 0])
        q[2] = (1 / (4 * q[0])) * (rot[0, 2] + rot[2, 0])
        q[3] = (1 / (4 * q[0])) * (rot[1, 2] - rot[2, 1])
    elif (rot[1, 1] >= T) and (rot[1, 1] >= rot[0, 0]) and (rot[1, 1] >= rot[2, 2]):
        q[1] = np.sqrt((1 + (2 * rot[1, 1]) - T) / 4)
        q[0] = (1 / (4 * q[1])) * (rot[0, 1] + rot[1, 0])
        q[2] = (1 / (4 * q[1])) * (rot[1, 2] + rot[2, 1])
        q[3] = (1 / (4 * q[1])) * (rot[2, 0] - rot[0, 2])
    elif (rot[2, 2] >= T) and (rot[2, 2] >= rot[0, 0]) and (rot[2, 2] >= rot[1, 1]):
        q[2] = np.sqrt((1 + (2 * rot[2, 2]) - T) / 4)
        q[0] = (1 / (4 * q[2])) * (rot[0, 2] + rot[2, 0])
        q[1] = (1 / (4 * q[2])) * (rot[1, 2] + rot[2, 1])
        q[3] = (1 / (4 * q[2])) * (rot[0, 1] - rot[1, 0])
    else:
        q[3] = np.sqrt((1 + T) / 4)
        q[0] = (1 / (4 * q[3])) * (rot[1, 2] - rot[2, 1])
        q[1] = (1 / (4 * q[3])) * (rot[2, 0] - rot[0, 2])
        q[2] = (1 / (4 * q[3])) * (rot[0, 1] - rot[1, 0])
    if q[3] < 0:
        q = -q
    # normalize and return
    return q / np.linalg.norm(q)


Azimuth = np.arange(0, 2 * np.pi, 0.5)
Elevation = np.arange(-np.pi / 2, np.pi / 2, 0.5)
R = 50
X, Y, Z = sph2cart(Azimuth, Elevation, R)
feat_posi_global = np.zeros((3, len(X)))
feat_posi_global[0, :] = X
feat_posi_global[1, :] = Y
feat_posi_global[2, :] = Z
Index = np.arange(0, len(X), 1)
Range = np.arange(0, 100000 - 1, 1)
ellipse_x = 10
ellipse_y = 10
z = 5
K1 = 5
K = np.pi / 10
t = np.arange(0, 500, 0.005)
dt = 0.005
dphi = np.pi/4
position = np.zeros((3, len(t)))
position[0, :] = ellipse_x * np.cos(K * t-dphi) 
position[1, :] = ellipse_y * np.sin(K * t-dphi) 
position[2, :] = z * np.sin(K1 * K * t-dphi) 

dp = np.zeros((3, len(t)))
dp[0, :] = -ellipse_x * K * np.sin(K * t-dphi)
dp[1, :] = ellipse_y * K * np.cos(K * t-dphi)
dp[2, :] = z * K1 * K * np.cos(K1 * K * t-dphi)
K2 = K * K
ddp = np.zeros((3, len(t)))
ddp[0, :] = -ellipse_x * K2 * np.cos(K * t-dphi)
ddp[1, :] = -ellipse_y * K2 * np.sin(K * t-dphi)
ddp[2, :] = -z * K1 * K1 * K2 * np.sin(K1 * K * t-dphi)
k_roll = 0.1
k_pitch = 0.2
eulerAngles = np.zeros((3, len(t)))
eulerAngles[0, :] = k_roll * np.cos(K * t)
eulerAngles[1, :] = k_pitch * np.sin(K * t)
eulerAngles[2, :] = K * t
eulerAnglesRates = np.zeros((3, len(t)))
eulerAnglesRates[0, :] = -k_roll * K * np.sin(K * t)
eulerAnglesRates[1, :] = k_pitch * K * np.cos(K * t)
eulerAnglesRates[2, :] = K
N_satelite = 10
s_p = np.zeros((3, N_satelite))
R_sate = 1000000
h_sate = 1000000
for i in range(N_satelite):
    theta = 2 * np.pi * i / N_satelite
    s_p[0, i] = R_sate * np.cos(theta)
    s_p[1, i] = R_sate * np.sin(theta)
    s_p[2, i] = h_sate

Rwb = euler2rot(eulerAngles)

imu_gyro = eulerRates2bodyRates(eulerAngles, eulerAnglesRates)

imu_acc = worldacc2bodyacc(Rwb, ddp)
feat_track = {}
wl = 10
R = Rwb[:, :, 0].T
v = np.array([[0], [K * ellipse_y], [K1 * K * z]])
p = np.array([[20], [5], [5]])
P = 0.1 * np.eye(9)

posi_estimate = np.zeros((3, len(t)))
posi_estimate[:, 0] = p.flatten()

g = np.array([[0], [0], [-9.8]])

Q = np.eye(12)
gyro_noise = 0.008
acc_noise = 0.019
gyro_random_walk = 0.0004
acc_random_walk = 0.05
Q[0:3, 0:3] = gyro_noise ** 2 * np.eye(3)
Q[3:6, 3:6] = acc_noise ** 2 * np.eye(3)
Q[6:9, 6:9] = gyro_random_walk ** 2 * np.eye(3)
Q[9:12, 9:12] = acc_random_walk ** 2 * np.eye(3)
Q = Q / dt
img_noise = 1.5/500#1.5
quat = rot_2_quat(R)
pose_total = {-1: {'R': R, 'p': p, 'v': v}}

Monte_count = 5
monte_range = range(Monte_count)
ticktoe = time.time_ns()
hno = 4
rng = np.random.default_rng(hno)
rints = rng.integers(1, 90000, Monte_count)
for k_monte in tqdm(monte_range):
    feat_track = {}
    ellipse_x = 10
    ellipse_y = 10
    z = 5
    K1 = 5
    K = np.pi / 10
    t = np.arange(0, 500, 0.005)
    dt = 0.005
    K2 = K * K
    k_roll = 0.1
    k_pitch = 0.2
    R = Rwb[:, :, 0].T
    v = dp[:, 0].reshape(3, 1)
    p = position[:, 0].reshape(3, 1)
    bg = np.zeros((3, 1))
    ba = np.zeros((3, 1))
    bg_true = np.zeros((3, 1))
    ba_true = np.zeros((3, 1))
    P = np.eye(15)
    P[0:3, 0:3] = 0.01 * np.eye(3)
    P[3:6, 3:6] = 0.1 * np.eye(3)
    P[6:9, 6:9] = 0.1 * np.eye(3)
    P[9:12, 9:12] = 0.000 * np.eye(3)
    P[12:15, 12:15] = 0.00 * np.eye(3)
    posi_estimate = np.zeros((3, len(t)))
    v_estimate = np.zeros((3, len(t)))
    R_estimate = np.zeros((3, 3, len(t)))
    P_estimate = np.zeros((15, 15, len(t)))
    bg_estimate = np.zeros((3, len(t)))
    ba_estimate = np.zeros((3, len(t)))
    posi_estimate[:, 0] = p.flatten()
    v_estimate[:, 0] = v.flatten()
    R_estimate[:, :, 0] = R
    P_estimate[:, :, 0] = P
    bg_estimate[:, 0] = bg.flatten()
    ba_estimate[:, 0] = ba.flatten()
    ticktoe1 = time.time_ns()
    ticktoe1 /= 100
    rand_n = ticktoe1 % 100000
    rng1 = np.random.default_rng(20*hno + 4 * k_monte+1)
    rng2 = np.random.default_rng(20*hno + 4 * k_monte+2)
    rng3 = np.random.default_rng(20*hno + 4 * k_monte+3)
    rng4 = np.random.default_rng(20*hno + 4 * k_monte+4)

    
    pose_total = {-1: {'R': R, 'p': p, 'v': v, 'bg': bg, 'ba': ba}}
    for k in tqdm(Range):
        acc_k = imu_acc[:, k].reshape(3, 1) + rng1.normal(0, acc_noise, (3, 1))/np.sqrt(dt) + ba_true
        gyro_k = imu_gyro[:, k].reshape(3, 1) + rng1.normal(0, gyro_noise, (3, 1))/np.sqrt(dt) + bg_true
        ba_true += rng2.normal(0, acc_random_walk, (3, 1))*np.sqrt(dt)
        bg_true += rng2.normal(0, gyro_random_walk, (3, 1))*np.sqrt(dt)
        xi_sum = compute_Xi_sum(dt, gyro_k, acc_k)
        xi_1 = xi_sum[:, 3:6]
        xi_2 = xi_sum[:, 6:9]
        xi_3 = xi_sum[:, 12:15]
        xi_4 = xi_sum[:, 15:18]
        Jrk_to_k1 = xi_sum[:, 9:12]
        Rk_to_k1 = xi_sum[:, 0:3]

        bg = pose_total[-1]['bg']
        ba = pose_total[-1]['ba']

        gyro_k = gyro_k - bg
        acc_k = acc_k - ba
        Gamma0 = gamma(-dt * gyro_k, 0)
        Gamma1 = gamma(dt * gyro_k, 1)
        Gamma2 = gamma(dt * gyro_k, 2)
        q_k2k1 = rot_2_quat(Rk_to_k1)
        R = pose_total[-1]['R']
        v = pose_total[-1]['v']
        p = pose_total[-1]['p']
        R_new = np.dot(Gamma0, R)
        v_new = v + g * dt + R.T @ Gamma1 @ acc_k * dt
        p_new = p + v * dt + 0.5 * g * (dt ** 2) + R.T @ Gamma2 @ acc_k * (dt ** 2)



        posi_estimate[:, k + 1] = p_new.flatten()


        F = np.zeros((15, 15))
        F[0:3, 0:3] = Gamma0
        F[3:6, 0:3] = -1 * R.T @ skew(Gamma1 @ acc_k * dt)
        F[3:6, 3:6] = np.eye(3)
        F[6:9, 0:3] = -1 * R.T @ skew(Gamma2 @ acc_k * (dt**2))
        F[6:9, 6:9] = np.eye(3)
        F[6:9, 3:6] = dt * np.eye(3)
        F[9:15, 9:15] = np.eye(6)
        G = np.zeros((15, 12))
        G[0:3, 0:3] = -1 * Gamma0 @ Jrk_to_k1 * dt
        G[3:6, 0:3] = 1 * R.T @ xi_3
        G[3:6, 3:6] = -1 *R.T @ xi_1
        G[6:9, 0:3] = 1 * R.T @ xi_4
        G[6:9, 3:6] = -1 * R.T @ xi_2
        G[9:15, 6:12] = np.eye(6)*dt

        F[0:9,9:15] = G[0:9,0:6]
        
        R = R_new
        v = v_new
        p = p_new
        pose_total[-1] = {'R': R, 'p': p, 'v': v, 'bg': bg, 'ba': ba}
        

        rows = np.size(P, 0)
        cols = np.size(P, 1)

        P[0:15, 0:15] = np.dot(np.dot(F, P[0:15, 0:15]), F.T)

        P21 = P[15:rows, 0:15]
        P22 = P[15:rows, 15:cols]

        P21 = np.dot(P21, F.T)

        P[15:rows, 0:15] = P21
        P[0:15, 15:cols] = P21.T
        P[15:rows, 15:cols] = P22


        P[0:15, 0:15] = P[0:15, 0:15] +  G @ Q @ G.T 

        P = 0.5 * (P + P.T)



        is_keyFrame = False
        # is_keyFrame = False
        if k % 20 == 0:
            is_keyFrame = True
        if is_keyFrame:
            pose_total[k + 1] = {'R': R, 'p': p}
            # P = np.block([
            #     [P, P[:, 0: 3], P[:, 6: 9]],
            #     [P[0: 3, :], P[0: 3, 0: 3], P[0: 3, 6: 9]],
            #     [P[6: 9, :], P[6: 9, 0: 3], P[6: 9, 6: 9]],
            # ])
            rows = np.size(P, 0)
            P_new = np.zeros((rows + 6, rows + 6))
            P_new[0:rows, 0:rows] = P
            P_new[0:rows, rows:rows + 3] = P[:, 0:3]
            P_new[0:rows, rows + 3:rows + 6] = P[:, 6:9]
            P_new[rows:rows + 3, 0:rows] = P[0:3, :]
            P_new[rows + 3:rows + 6, 0:rows] = P[6:9, :]
            P_new[rows:rows + 3, rows:rows + 3] = P[0:3, 0:3]
            P_new[rows:rows + 3, rows + 3:rows + 6] = P[0:3, 6:9]
            P_new[rows + 3:rows + 6, rows:rows + 3] = P[6:9, 0:3]
            P_new[rows + 3:rows + 6, rows + 3:rows + 6] = P[6:9, 6:9]
            P = P_new

            feat_posi_body = np.dot(Rwb[:, :, k + 1].T, feat_posi_global - position[:, k + 1].reshape(3, 1))
            key = np.where(feat_posi_body[2, :] > 0)
            feat_front_body = feat_posi_body[:, key[0]]
            feat_front_uv = feat_front_body[0:2, :] / feat_front_body[2, :]
            fov = np.sqrt(feat_front_uv[0, :] ** 2 + feat_front_uv[1, :] ** 2)
            key2 = np.where(fov < 1)
            feat_front_uv_inview = feat_front_uv[:, key2[0]]
            feat_id = Index[key[0][key2[0]]]

            feat_lost = {}
            for key in list(feat_track.keys()):
                if key not in feat_id:
                    feat_lost[key] = feat_track[key]
                    feat_track.pop(key)

            for kk in np.arange(0, np.size(feat_id)):
                _id = feat_id[kk]
                if _id not in feat_track:
                    feat_track[_id] = {}
                feat_track[_id][k + 1] = feat_front_uv_inview[:, kk] + rng2.normal(0, img_noise, (2, ))
            feat_marg = {}
            for key in list(feat_track.keys()):
                if len(feat_track[key]) > wl:
                    feat_marg[key] = feat_track[key]
                    feat_track.pop(key)

            feat_update_posi = {}
            for key in feat_marg.keys():
                feat_uv_i = feat_marg[key]
                pf_G, is_valid = triangulate_multi_initial_guess(feat_uv_i, pose_total)
                if not is_valid:
                    continue
                pf_Gnew, is_valid = triangulate_gauss_newton(pf_G, pose_total, feat_uv_i)
                if not is_valid:
                    continue
                feat_update_posi[key] = pf_Gnew
            H_X = np.empty((0, 15 + 6 * (len(pose_total.keys()) - 1)))
            Residual = np.empty((0, 1))
            pose_id_list = list(pose_total.keys())
            pose_id_list.sort()
            for key in feat_update_posi.keys():
                rows = len(feat_marg[key].keys()) * 2
                cols = 15 + 6 * (len(pose_total.keys()) - 1)
                anchor_frame_id = min(feat_marg[key].keys())
                anchor_index = pose_id_list.index(anchor_frame_id) - 1
                H_pose = np.zeros((rows, cols))
                H_feat = np.zeros((rows, 3))
                feat_xyz_G_i = feat_update_posi[key]
                uv_pred = np.zeros((rows, 1))
                uv_meas = np.zeros((rows, 1))
                row_count = 0
                for frame_id in feat_marg[key].keys():
                    x_c = pose_total[frame_id]['R'] @ (feat_xyz_G_i - pose_total[frame_id]['p'].reshape(3, 1))
                    H_proj = np.array([[1 / x_c[2][0], 0, -x_c[0][0] / (x_c[2][0] ** 2)],
                                    [0, 1 / x_c[2][0], -x_c[1][0] / (x_c[2][0] ** 2)]])
                    H_pose_block = np.zeros((3, cols))
                    H_x_block = np.zeros((3, 6))
                    H_x_block[0:3, 0:3] = skew(x_c)
                    H_x_block[0:3, 3:6] = -1 * pose_total[frame_id]['R']
                    frame_index = pose_id_list.index(frame_id) - 1
                    H_pose_block[:, 15 + 6 * frame_index:21 + 6 * frame_index] += H_x_block
                    H_pose[row_count:row_count + 2, :] = H_proj @ H_pose_block
                    H_feat[row_count:row_count + 2, :] = H_proj @ pose_total[frame_id]['R']
                    uv_pred[row_count:row_count + 2] = x_c[0:2] / x_c[2]
                    uv_meas[row_count:row_count + 2] = feat_marg[key][frame_id].reshape(2, 1)
                    row_count += 2
                residual = uv_meas - uv_pred 
                Q_feat, R_feat = qr(H_feat)
                Q_feat = Q_feat[:, 3:]
                H_pose = Q_feat.T @ H_pose
                residual = Q_feat.T @ residual
                H_X = np.vstack((H_X, H_pose))
                Residual = np.vstack((Residual, residual))
            if len(feat_update_posi) > 0:
                if H_X.shape[0] > H_X.shape[1]:
                    Q_X, R_X = qr(H_X)
                    H_X = R_X[0:H_X.shape[1], :]
                    Q_X = Q_X[:, 0:H_X.shape[1]]
                    Residual = Q_X.T @ Residual
                R_noise = 1 * img_noise** 2 * np.eye(H_X.shape[0])
                K = P @ H_X.T @ np.linalg.inv(H_X @ P @ H_X.T + R_noise)
                eye = np.eye(P.shape[0])
                P = (eye - K @ H_X) @ P @ (eye - K @ H_X).T + K @ R_noise @ K.T
                delta_X = K @ Residual

                R = pose_total[-1]['R']
                v = pose_total[-1]['v']
                p = pose_total[-1]['p']
                bg = pose_total[-1]['bg']
                ba = pose_total[-1]['ba']
                quat = np.zeros((4,1))
                quat[1:4] = 0.5 * delta_X[0:3]
                quat[0,0] = 1
                quat = quat / np.linalg.norm(quat)
                dR = quat_2_Rot(quat)
                dR2 = expm(skew(-1 * delta_X[0:3]))
                R_new = dR2 @ R
                v_new = v + delta_X[3:6].reshape(3, 1)
                p_new = p + delta_X[6:9].reshape(3, 1)
                bg_new = bg + delta_X[9:12].reshape(3, 1)
                ba_new = ba + delta_X[12:15].reshape(3, 1)
                
                pose_total[-1] = {'R': R_new, 'p': p_new, 'v': v_new, 'bg': bg_new, 'ba': ba_new}
                for key in pose_total.keys():
                    if key == -1:
                        continue
                    key_index = pose_id_list.index(key) - 1
                    quat = np.zeros((4, 1))
                    quat[1:4] = 0.5 * delta_X[15 + 6 * key_index:18 + 6 * key_index]
                    quat[0, 0] = 1
                    quat = quat / np.linalg.norm(quat)
                    dR = quat_2_Rot(quat)
                    dR2 = expm(skew(-1 *delta_X[15 + 6 * key_index:18 + 6 * key_index]))
                    R = pose_total[key]['R']
                    p = pose_total[key]['p']
                    R_new = dR2 @ R
                    p_new =  p + delta_X[18 + 6 * key_index:21 + 6 * key_index].reshape(3, 1)
                    pose_total[key] = {'R': R_new, 'p': p_new}


            if len(pose_total) > wl + 1:
                key_marg = pose_id_list[1: len(pose_total) - wl]
                for key in key_marg:
                    pose_total.pop(key)
                for key in feat_track.keys():
                    for key2 in key_marg:
                        if key2 in feat_track[key]:
                            feat_track[key].pop(key2)
                P_rows = np.size(P, 0)
                P_cols = np.size(P, 1)
                P_new = np.zeros((P_rows - 6, P_cols - 6))
                P_new[0:15, 0:15] = P[0:15, 0:15]
                P_new[0:15, 15:] = P[0:15, 21:]
                P_new[15:, 0:15] = P[21:, 0:15]
                P_new[15:, 15:] = P[21:, 21:]
                P = P_new

            x_mesa = position[2, k + 1]
            x_pred = pose_total[-1]['p'][2][0]
            residual = x_mesa - x_pred + rng3.normal(0, 0.5, (1, 1))
            residual = residual * np.eye(1)
            H = np.zeros((1, 15 + 6 * (len(pose_total.keys()) - 1)))
            H[0, 8] = 1
            R_noise = 0.25 * np.eye(1)
            K = P @ H.T @ np.linalg.inv(H @ P @ H.T + R_noise)
            eye = np.eye(P.shape[0])
            P = (eye - K @ H) @ P @ (eye - K @ H).T + K @ R_noise @ K.T
            delta_X = K @ residual
            R = pose_total[-1]['R']
            v = pose_total[-1]['v']
            p = pose_total[-1]['p']
            bg = pose_total[-1]['bg']
            ba = pose_total[-1]['ba']
            quat = np.zeros((4,1))
            quat[1:4] = 0.5 * delta_X[0:3]
            quat[0,0] = 1
            quat = quat / np.linalg.norm(quat)
            dR = quat_2_Rot(quat)
            dR2 = expm(skew(-1 * delta_X[0:3]))
            R_new = dR2 @ R
            v_new = v + delta_X[3:6].reshape(3, 1)
            p_new = p + delta_X[6:9].reshape(3, 1)
            bg_new = bg + delta_X[9:12].reshape(3, 1)
            ba_new = ba + delta_X[12:15].reshape(3, 1)  
            pose_total[-1] = {'R': R_new, 'p': p_new, 'v': v_new, 'bg': bg_new, 'ba': ba_new}
            pose_id_list = list(pose_total.keys())
            pose_id_list.sort()
            for key in pose_total.keys():
                if key == -1:
                    continue
                key_index = pose_id_list.index(key) - 1
                quat = np.zeros((4, 1))
                quat[1:4] = 0.5 * delta_X[15 + 6 * key_index:18 + 6 * key_index]
                quat[0, 0] = 1
                quat = quat / np.linalg.norm(quat)
                dR = quat_2_Rot(quat)
                dR2 = expm(skew(-1 *delta_X[15 + 6 * key_index:18 + 6 * key_index]))
                R = pose_total[key]['R']
                p = pose_total[key]['p']
                R_new = dR2 @ R
                p_new =  p + delta_X[18 + 6 * key_index:21 + 6 * key_index].reshape(3, 1)
                pose_total[key] = {'R': R_new, 'p': p_new}

            pseduo_range_mesa = np.sqrt(np.sum((s_p - position[:, k + 1].reshape((3, 1))) ** 2, axis=0))
            p_r_pred = np.sqrt(np.sum((s_p - pose_total[-1]['p'].reshape((3, 1))) ** 2, axis=0))
            residual = pseduo_range_mesa - p_r_pred
            #residual += rng4.normal(0, 10, residual.shape)
            n_s_r = s_p - pose_total[-1]['p'].reshape((3, 1))
            # divide by column
            n_s_r = n_s_r / np.linalg.norm(n_s_r, axis=0)
            n_s_r = n_s_r.T
            rows = residual.shape[0]
            #residual = np.zeros((rows, 1))
            residual = residual.reshape((rows, 1))
            residual = residual + rng4.normal(0, 10, residual.shape)
            H = np.zeros((rows, 15 + 6 * (len(pose_total.keys()) - 1)))
            H[:, 6:9] = -1 * n_s_r
            R_noise = np.eye(rows) * 100
            K = P @ H.T @ np.linalg.inv(H @ P @ H.T + R_noise)
            eye = np.eye(P.shape[0])
            P = (eye - K @ H) @ P @ (eye - K @ H).T + K @ R_noise @ K.T
            delta_X = K @ residual
            R = pose_total[-1]['R']
            v = pose_total[-1]['v']
            p = pose_total[-1]['p']
            bg = pose_total[-1]['bg']
            ba = pose_total[-1]['ba']
            quat = np.zeros((4,1))
            quat[1:4] = 0.5 * delta_X[0:3]
            quat[0,0] = 1
            quat = quat / np.linalg.norm(quat)
            dR = quat_2_Rot(quat)
            dR2 = expm(skew(-1 * delta_X[0:3]))
            R_new = dR2 @ R
            v_new = v + delta_X[3:6].reshape(3, 1)
            p_new = p + delta_X[6:9].reshape(3, 1)
            bg_new = bg + delta_X[9:12].reshape(3, 1)
            ba_new = ba + delta_X[12:15].reshape(3, 1)
            pose_total[-1] = {'R': R_new, 'p': p_new, 'v': v_new, 'bg': bg_new, 'ba': ba_new}
            pose_id_list = list(pose_total.keys())
            pose_id_list.sort()
            for key in pose_total.keys():
                if key == -1:
                    continue
                key_index = pose_id_list.index(key) - 1
                quat = np.zeros((4, 1))
                quat[1:4] = 0.5 * delta_X[15 + 6 * key_index:18 + 6 * key_index]
                quat[0, 0] = 1
                quat = quat / np.linalg.norm(quat)
                dR = quat_2_Rot(quat)
                dR2 = expm(skew(-1 *delta_X[15 + 6 * key_index:18 + 6 * key_index]))
                R = pose_total[key]['R']
                p = pose_total[key]['p']
                R_new = dR2 @ R
                p_new =  p + delta_X[18 + 6 * key_index:21 + 6 * key_index].reshape(3, 1)
                pose_total[key] = {'R': R_new, 'p': p_new}

        R = pose_total[-1]['R']
        v = pose_total[-1]['v']
        p = pose_total[-1]['p']
        posi_estimate[:, k + 1] = p.flatten()
        v_estimate[:, k + 1] = v.flatten()
        R_estimate[:, :, k + 1] = R
        P_estimate[:, :, k + 1] = P[0:15, 0:15]
    # fig = plt.figure()
    # ax = fig.add_subplot(311)
    # ax.plot(t, posi_estimate[0, :], label='x')
    # ax.plot(t, position[0, :], label='x_truth')
    # ax.legend()
    # ax = fig.add_subplot(312)
    # ax.plot(t, posi_estimate[1, :], label='y')
    # ax.plot(t, position[1, :], label='y_truth')
    # ax.legend()
    # ax = fig.add_subplot(313)
    # ax.plot(t, posi_estimate[2, :], label='z')
    # ax.plot(t, position[2, :], label='z_truth')
    # ax.legend()
    # plt.show()
    filename = 'datConGBVIO10/datapose_total' + str(hno)+'_' +str(k_monte)+ '.npz'
    np.savez(filename,posi_estimate=posi_estimate, v_estimate=v_estimate, R_estimate=R_estimate, P_estimate=P_estimate)

filename = 'datConGBVIO10/datapose_true.npz'
np.savez(filename,posi_true=position, v_true=dp, R_true=Rwb,t=t)
