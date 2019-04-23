
import os
from concurrent.futures import ProcessPoolExecutor
import subprocess
import shlex
# from micro_dl.cli.metrics_script import compute_metrics

def multiprocessing(func, args, n_workers = 8):
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        executor.map(func, args)

def sub_process(argin):
    p = subprocess.Popen(argin)
    p.wait()
    print(p.stdout)

if __name__ == '__main__':
    model_path = '/flexo/ComputationalMicroscopy/Projects/virtualstaining/kidneyslice/' \
                 '2019_02_15_kidney_slice/models_kidney_20190215'
    model_dirs = ['2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ret_568_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ori_x_568_augmented_tf_20',
                  '2D_tile256_step128_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ori_y_568_augmented_tf_20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_trans_568_augmented_tf_20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_scat_568_augmented_tf_20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ret+trans_568_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ret+ori_x+ori_y_568_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ret+ori_x+ori_y+trans_568_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ret+ori_x+ori_y+trans+scat_568_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ret_405_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ori_x_405_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ori_y_405_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_trans_405_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_scat_405_augmented_tf_20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ret+trans_405_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ret+ori_x+ori_y_405_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e-5_6e-3_fltr16_256_do20_MSE_chan_ret+ori_x+ori_y+trans_405_augmented_tf20',
                  '2D_tile256_step128_registered_masked_clr_5e - 5_6e-3_fltr16_256_do20_MSE_chan_ret + ori_x + ori_y + trans + scat_405_augmented_tf20'
                  ]
    argin_list = []
    for model_dir in model_dirs:
        model_path = '/flexo/ComputationalMicroscopy/Projects/virtualstaining/kidneyslice/' \
                     '2019_02_15_kidney_slice/models_kidney_20190215'
        image_path = '/data/sguo/Processed/2019_02_15_kidney_slice/SMS_2018_1227_1433_1_BG_2019_0215_1337_1_registered/'
        argin = ''.join(['python /microDL/micro_dl/cli/metrics_script.py --model_dir ', os.path.join(model_path, model_dir)
                            , ' --test_data ', '--image_dir ', image_path, ' --metrics ', 'ssim corr r2',
                         ' --orientations ', 'xy xz yz xyz'])
        argin = shlex.split(argin)
        argin_list.append(argin)

    multiprocessing(sub_process, argin_list, n_workers=8)