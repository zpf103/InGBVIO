/**  This File is part of InGVIO, an invariant filter for mono/stereo visual-
 *    inertial-raw GNSS navigation. 
 *    
 *    Copyright (C) 2022  Changwu Liu (cwliu529@163.com,
 *                                     lcw18@mails.tsinghua.edu.cn (valid until 2023))
 *    
 *    This program is free software: you can redistribute it and/or modify
 *    it under the terms of the GNU General Public License as published by
 *    the Free Software Foundation, either version 3 of the License, or
 *    (at your option) any later version.
 *    
 *    This program is distributed in the hope that it will be useful,
 *    but WITHOUT ANY WARRANTY; without even the implied warranty of
 *    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *    GNU General Public License for more details.
 *    
 *    You should have received a copy of the GNU General Public License
 *    along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

#pragma once

#include <Eigen/Core>
#include <Eigen/Geometry>
#include <string>

#include <ros/ros.h>
#include <opencv2/highgui/highgui.hpp>

namespace ingvio
{
    class IngvioParams
    {
    public:
        IngvioParams() : _T_cl2i(Eigen::Isometry3d::Identity()), _T_cr2i(Eigen::Isometry3d::Identity()) {}
        
        IngvioParams(const IngvioParams&) = delete;
        
        IngvioParams operator=(const IngvioParams&) = delete;
        
        ~IngvioParams() = default;
        
        std::string _config_path;
        
        int _cam_nums;
        std::string _cam_left_config_path;
        std::string _cam_right_config_path;
        
        Eigen::Isometry3d _T_cl2i, _T_cr2i;
        
        std::string _feature_topic;
        std::string _imu_topic;
        std::string _gps_fix_topic;
        std::string _baro_topic;
        
        int _max_sw_clones;
        int _is_key_frame;
        int _max_lm_feats;
        int _enable_gnss;
        
        double _noise_g;
        double _noise_a;
        double _noise_bg;
        double _noise_ba;
        double _noise_clockbias;
        double _noise_cb_rw;
        
        double _init_cov_rot;
        double _init_cov_pos;
        double _init_cov_vel;
        double _init_cov_bg;
        double _init_cov_ba;
        double _init_cov_ext_rot;
        double _init_cov_ext_pos;
        double _init_cov_rcv_clockbias;
        double _init_cov_rcv_clockbias_randomwalk;
        double _init_cov_yof;
        
        double _init_gravity;
        int _max_imu_buffer_size;
        int _init_imu_buffer_sp;
        int _max_baro_buffer_size;

        
        double _trans_thres;
        double _huber_epsilon;
        double _conv_precision;
        double _init_damping;
        int _outer_loop_max_iter;
        int _inner_loop_max_iter;
        double _max_depth;
        double _min_depth;
        double _max_baseline_ratio;
        
        int _chi2_max_dof;
        double _chi2_thres;
        double _visual_noise;
        
        int _frame_select_interval;
        
        std::string _gnss_ephem_topic;
        std::string _gnss_glo_ephem_topic;
        std::string _gnss_meas_topic;
        std::string _gnss_iono_params_topic;
        std::string _rtk_gt_topic;
        
        double _gnss_elevation_thres;
        double _gnss_psr_std_thres;
        double _gnss_dopp_std_thres;
        int _gnss_track_num_thres;
        
        int _use_fix_time_offset;
        double _gnss_local_offset;
        int _is_gnss_chi2_test;
        int _is_gnss_strong_reject;
        
        int _gv_align_batch_size;
        int _gv_align_max_iter;
        double _gv_align_conv_epsilon;
        double _gv_align_vel_thres;
        
        double _psr_noise_amp;
        double _dopp_noise_amp;
        int _is_adjust_yof;
        
        void readParams(ros::NodeHandle& nh);
        void readParams(const std::string& config_path);
        
        void printParams();
        
        template <typename T>
        static T readParams(ros::NodeHandle& n, std::string name);
    };
    
    template <typename T>
    T IngvioParams::readParams(ros::NodeHandle& n, std::string name)
    {
        T ans;
        
        if (n.getParam(name, ans))
        {
            ROS_INFO_STREAM("Loaded " << name << ": " << ans);    
        }
        else
        {
            ROS_ERROR_STREAM("Failed to load: " << name);
            n.shutdown();
        }
        
        return ans;
    }
}
